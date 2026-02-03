"""
Tests for script parameter parsing utilities.

These tests verify the parse_script_parameters function and related utilities
for extracting and validating parameters from script content.
"""
import pytest
from app.utils.script_params import (
    parse_script_parameters,
    detect_parameter_type,
    generate_description,
    validate_parameter_name,
    validate_parameter_value,
    mask_password_values,
)


class TestParseScriptParameters:
    """Test the parse_script_parameters function"""

    def test_parse_empty_script(self):
        """Test parsing an empty script returns empty list"""
        result = parse_script_parameters("")
        assert result == []

    def test_parse_none_script(self):
        """Test parsing None returns empty list"""
        result = parse_script_parameters(None)
        assert result == []

    def test_parse_single_parameter_no_default(self):
        """Test parsing a single parameter without default value"""
        script = "echo ${DB_HOST}"
        result = parse_script_parameters(script)
        
        assert len(result) == 1
        assert result[0]['name'] == 'DB_HOST'
        assert result[0]['type'] == 'text'
        assert result[0]['default'] == ''
        assert result[0]['required'] is True
        assert 'description' in result[0]

    def test_parse_single_parameter_with_default(self):
        """Test parsing a single parameter with default value"""
        script = "echo ${DB_HOST:-localhost}"
        result = parse_script_parameters(script)
        
        assert len(result) == 1
        assert result[0]['name'] == 'DB_HOST'
        assert result[0]['type'] == 'text'
        assert result[0]['default'] == 'localhost'
        assert result[0]['required'] is False

    def test_parse_multiple_parameters(self):
        """Test parsing multiple different parameters"""
        script = """
        DB_HOST=${DB_HOST:-localhost}
        DB_PORT=${DB_PORT:-5432}
        DB_NAME=${DB_NAME}
        """
        result = parse_script_parameters(script)
        
        assert len(result) == 3
        
        # Check sorted by name
        names = [p['name'] for p in result]
        assert names == sorted(names)
        
        # Check DB_HOST
        db_host = next(p for p in result if p['name'] == 'DB_HOST')
        assert db_host['default'] == 'localhost'
        assert db_host['required'] is False
        
        # Check DB_NAME (no default)
        db_name = next(p for p in result if p['name'] == 'DB_NAME')
        assert db_name['default'] == ''
        assert db_name['required'] is True

    def test_parse_duplicate_parameters(self):
        """Test that duplicate parameters are deduplicated"""
        script = """
        echo ${DB_HOST}
        echo ${DB_HOST}
        echo ${DB_HOST:-localhost}
        """
        result = parse_script_parameters(script)
        
        # Should only have one DB_HOST entry
        assert len(result) == 1
        assert result[0]['name'] == 'DB_HOST'
        # Should use the default from the third occurrence
        assert result[0]['default'] == 'localhost'
        assert result[0]['required'] is False

    def test_parse_password_parameters(self):
        """Test that password-type parameters are detected"""
        script = """
        DB_PASSWORD=${DB_PASSWORD}
        API_KEY=${API_KEY}
        SECRET_TOKEN=${SECRET_TOKEN}
        DB_HOST=${DB_HOST}
        """
        result = parse_script_parameters(script)
        
        # Find password-type parameters
        password_params = [p for p in result if p['type'] == 'password']
        text_params = [p for p in result if p['type'] == 'text']
        
        assert len(password_params) == 3
        password_names = {p['name'] for p in password_params}
        assert password_names == {'DB_PASSWORD', 'API_KEY', 'SECRET_TOKEN'}
        
        assert len(text_params) == 1
        assert text_params[0]['name'] == 'DB_HOST'

    def test_parse_parameter_with_special_chars_in_default(self):
        """Test parsing parameters with special characters in default values"""
        script = 'URL=${URL:-https://example.com:8080/api}'
        result = parse_script_parameters(script)
        
        assert len(result) == 1
        assert result[0]['name'] == 'URL'
        assert result[0]['default'] == 'https://example.com:8080/api'

    def test_parse_parameter_with_spaces_in_default(self):
        """Test parsing parameters with spaces in default values"""
        script = 'MESSAGE=${MESSAGE:-Hello World}'
        result = parse_script_parameters(script)
        
        assert len(result) == 1
        assert result[0]['name'] == 'MESSAGE'
        assert result[0]['default'] == 'Hello World'

    def test_parse_invalid_parameter_names_ignored(self):
        """Test that invalid parameter names (not UPPER_SNAKE_CASE) are ignored"""
        script = """
        ${VALID_PARAM}
        ${lowercase}
        ${MixedCase}
        ${123_INVALID}
        """
        result = parse_script_parameters(script)
        
        # Only VALID_PARAM should be parsed
        assert len(result) == 1
        assert result[0]['name'] == 'VALID_PARAM'

    def test_parse_parameters_with_numbers(self):
        """Test parsing parameters with numbers in the name"""
        script = """
        ${DB_HOST_1}
        ${API_V2_KEY}
        ${BACKUP_DIR_123}
        """
        result = parse_script_parameters(script)
        
        assert len(result) == 3
        names = {p['name'] for p in result}
        assert names == {'DB_HOST_1', 'API_V2_KEY', 'BACKUP_DIR_123'}

    def test_parse_complex_script(self):
        """Test parsing a complex real-world script"""
        script = """#!/bin/bash
        # Backup script with parameters
        
        BACKUP_DIR=${BACKUP_DIR:-/backups}
        DB_HOST=${DB_HOST}
        DB_PORT=${DB_PORT:-5432}
        DB_NAME=${DB_NAME}
        DB_USER=${DB_USER:-postgres}
        DB_PASSWORD=${DB_PASSWORD}
        
        echo "Connecting to ${DB_HOST}:${DB_PORT}"
        pg_dump -h ${DB_HOST} -p ${DB_PORT} -U ${DB_USER} ${DB_NAME} > ${BACKUP_DIR}/backup.sql
        """
        result = parse_script_parameters(script)
        
        assert len(result) == 6
        
        # Verify password detection
        db_password = next(p for p in result if p['name'] == 'DB_PASSWORD')
        assert db_password['type'] == 'password'
        assert db_password['required'] is True
        
        # Verify defaults
        backup_dir = next(p for p in result if p['name'] == 'BACKUP_DIR')
        assert backup_dir['default'] == '/backups'
        assert backup_dir['required'] is False


class TestDetectParameterType:
    """Test the detect_parameter_type function"""

    def test_detect_password_type(self):
        """Test detecting password-type parameters"""
        assert detect_parameter_type('DB_PASSWORD') == 'password'
        assert detect_parameter_type('API_KEY') == 'password'
        assert detect_parameter_type('SECRET_TOKEN') == 'password'
        assert detect_parameter_type('AUTH_SECRET') == 'password'
        assert detect_parameter_type('MY_PASSPHRASE') == 'password'
        assert detect_parameter_type('MY_CREDENTIALS') == 'password'
        assert detect_parameter_type('AWS_CREDENTIAL') == 'password'

    def test_detect_text_type(self):
        """Test detecting text-type parameters"""
        assert detect_parameter_type('DB_HOST') == 'text'
        assert detect_parameter_type('DB_PORT') == 'text'
        assert detect_parameter_type('BACKUP_DIR') == 'text'
        assert detect_parameter_type('USERNAME') == 'text'


class TestGenerateDescription:
    """Test the generate_description function"""

    def test_generate_description_text_param(self):
        """Test that descriptions are no longer auto-generated (returns empty)"""
        desc = generate_description('DB_HOST', 'text')
        assert desc == ''

    def test_generate_description_password_param(self):
        """Test that password descriptions are no longer auto-generated (returns empty)"""
        desc = generate_description('DB_PASSWORD', 'password')
        assert desc == ''

    def test_generate_description_api_key(self):
        """Test that API key descriptions are no longer auto-generated (returns empty)"""
        desc = generate_description('API_KEY', 'password')
        assert desc == ''


class TestValidateParameterName:
    """Test the validate_parameter_name function"""

    def test_valid_names(self):
        """Test valid parameter names"""
        assert validate_parameter_name('DB_HOST') is True
        assert validate_parameter_name('API_KEY_123') is True
        assert validate_parameter_name('_PRIVATE_VAR') is True
        assert validate_parameter_name('BACKUP_DIR') is True

    def test_invalid_names(self):
        """Test invalid parameter names"""
        assert validate_parameter_name('lowercase') is False
        assert validate_parameter_name('MixedCase') is False
        assert validate_parameter_name('123_INVALID') is False
        assert validate_parameter_name('') is False
        assert validate_parameter_name(None) is False
        assert validate_parameter_name('WITH-DASH') is False
        assert validate_parameter_name('WITH SPACE') is False


class TestValidateParameterValue:
    """Test the validate_parameter_value function"""

    def test_required_parameter_with_value(self):
        """Test required parameter with a value"""
        param_def = {'name': 'DB_HOST', 'required': True}
        valid, error = validate_parameter_value(param_def, 'localhost')
        assert valid is True
        assert error is None

    def test_required_parameter_without_value(self):
        """Test required parameter without a value"""
        param_def = {'name': 'DB_HOST', 'required': True}
        valid, error = validate_parameter_value(param_def, '')
        assert valid is False
        assert 'required' in error.lower()
        assert 'DB_HOST' in error

    def test_required_parameter_with_none(self):
        """Test required parameter with None value"""
        param_def = {'name': 'DB_HOST', 'required': True}
        valid, error = validate_parameter_value(param_def, None)
        assert valid is False
        assert 'required' in error.lower()

    def test_optional_parameter_without_value(self):
        """Test optional parameter without a value"""
        param_def = {'name': 'DB_PORT', 'required': False}
        valid, error = validate_parameter_value(param_def, '')
        assert valid is True
        assert error is None


class TestMaskPasswordValues:
    """Test the mask_password_values function"""

    def test_mask_password_values(self):
        """Test masking password-type parameter values"""
        parameters = [
            {'name': 'DB_HOST', 'type': 'text'},
            {'name': 'DB_PASSWORD', 'type': 'password'},
            {'name': 'API_KEY', 'type': 'password'},
        ]
        
        parameter_values = {
            'DB_HOST': 'localhost',
            'DB_PASSWORD': 'secret123',
            'API_KEY': 'key-abc-xyz',
        }
        
        masked = mask_password_values(parameters, parameter_values)
        
        assert masked['DB_HOST'] == 'localhost'  # Not masked
        assert masked['DB_PASSWORD'] == '***'  # Masked
        assert masked['API_KEY'] == '***'  # Masked

    def test_mask_empty_values(self):
        """Test masking with empty parameter values"""
        parameters = [
            {'name': 'DB_PASSWORD', 'type': 'password'},
        ]
        
        result = mask_password_values(parameters, {})
        assert result == {}

    def test_mask_none_values(self):
        """Test masking with None parameter values"""
        parameters = [
            {'name': 'DB_PASSWORD', 'type': 'password'},
        ]
        
        result = mask_password_values(parameters, None)
        assert result == {}

    def test_mask_only_non_empty_passwords(self):
        """Test that only non-empty password values are masked"""
        parameters = [
            {'name': 'DB_PASSWORD', 'type': 'password'},
        ]
        
        parameter_values = {
            'DB_PASSWORD': '',
        }
        
        masked = mask_password_values(parameters, parameter_values)
        # Empty password should remain empty (not masked as '***')
        assert masked['DB_PASSWORD'] == ''
