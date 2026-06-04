import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.features import (
    FEATURES,
    Plan,
    get_current_plan,
    plan_includes,
    require_feature,
)
from app.database.models import LicensingState


@pytest.mark.unit
class TestPlanIncludes:
    @pytest.mark.parametrize(
        ("current", "required", "expected"),
        [
            (Plan.COMMUNITY, Plan.COMMUNITY, True),
            (Plan.PRO, Plan.COMMUNITY, True),
            (Plan.ENTERPRISE, Plan.PRO, True),
            (Plan.COMMUNITY, Plan.PRO, False),
            (Plan.PRO, Plan.ENTERPRISE, False),
        ],
    )
    def test_plan_includes(self, current, required, expected):
        assert plan_includes(current, required) is expected


@pytest.mark.unit
class TestCurrentPlan:
    def test_get_current_plan_defaults_to_community_when_missing_settings(
        self, db_session: Session
    ):
        assert get_current_plan(db_session) == Plan.COMMUNITY

    def test_get_current_plan_uses_saved_value(self, db_session: Session):
        db_session.add(
            LicensingState(
                instance_id="test-instance-core-features-enterprise",
                plan="enterprise",
                status="active",
            )
        )
        db_session.commit()

        assert get_current_plan(db_session) == Plan.ENTERPRISE

    def test_get_current_plan_defaults_inactive_state_to_community(
        self, db_session: Session
    ):
        db_session.add(
            LicensingState(
                instance_id="test-instance-core-features-inactive",
                plan="pro",
                status="none",
            )
        )
        db_session.commit()

        assert get_current_plan(db_session) == Plan.COMMUNITY


@pytest.mark.unit
class TestRequireFeature:
    def test_require_feature_rejects_unknown_feature(self, db_session: Session):
        dependency = require_feature("unknown_feature").dependency

        with pytest.raises(ValueError, match="Unknown feature"):
            dependency(db_session)

    def test_require_feature_allows_included_plan(self, db_session: Session):
        db_session.add(
            LicensingState(
                instance_id="test-instance-core-features-rbac",
                plan="enterprise",
                status="active",
            )
        )
        db_session.commit()

        dependency = require_feature("rbac").dependency

        assert dependency(db_session) is None

    def test_require_feature_blocks_missing_plan(self, db_session: Session):
        db_session.add(
            LicensingState(
                instance_id="test-instance-core-features-community",
                plan="community",
                status="active",
            )
        )
        db_session.commit()

        dependency = require_feature("borg_v2").dependency

        with pytest.raises(HTTPException) as exc:
            dependency(db_session)

        assert exc.value.status_code == 403
        assert exc.value.detail == {
            "key": "backend.errors.plan.featureNotAvailable",
            "feature": "borg_v2",
            "required": FEATURES["borg_v2"].value,
            "current": Plan.COMMUNITY.value,
        }
