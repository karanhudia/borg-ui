import type { PlanContentFeature, PlanContentManifest } from '../types/planContent'
import { BASE_PATH } from '../utils/basePath'

export const LOCAL_PLAN_CONTENT_URL = `${BASE_PATH}/plan-content.json`
const DEFAULT_REMOTE_PLAN_CONTENT_URL = 'https://karanhudia.github.io/borg-ui/plan-content.json'

export const DEFAULT_PLAN_CONTENT_MANIFEST: PlanContentManifest = {
  version: 1,
  generated_at: '2026-04-07T00:00:00Z',
  features: [
    {
      id: 'borg_v2',
      plan: 'pro',
      label: 'Borg v2 backups',
      label_localized: {
        de: 'Borg v2-Backups',
        es: 'Copias de seguridad Borg v2',
        it: 'Backup Borg v2',
      },
      description: 'Next-generation Borg format with improved deduplication and performance',
      description_localized: {
        de: 'Borg-Format der nächsten Generation mit verbesserter Deduplizierung und Leistung',
        es: 'Formato Borg de nueva generación con deduplicación y rendimiento mejorados',
        it: 'Formato Borg di nuova generazione con deduplicazione e prestazioni migliorate',
      },
    },
    {
      id: 'multi_user',
      plan: 'community',
      label: 'Multiple user accounts',
      label_localized: {
        de: 'Mehrere Benutzerkonten',
        es: 'Varias cuentas de usuario',
        it: 'Più account utente',
      },
      description: 'Invite additional users to manage backups with their own login',
      description_localized: {
        de: 'Laden Sie weitere Benutzer ein, Backups mit eigenem Login zu verwalten',
        es: 'Invita a usuarios adicionales a gestionar copias de seguridad con su propio acceso',
        it: 'Invita altri utenti a gestire i backup con il proprio accesso',
      },
    },
    {
      id: 'extra_users',
      plan: 'pro',
      label: 'Expanded user seats',
      label_localized: {
        de: 'Erweiterte Benutzerplätze',
        es: 'Plazas de usuario ampliadas',
        it: 'Posti utente ampliati',
      },
      description: 'Add more than 5 users, with up to 10 seats on Pro',
      description_localized: {
        de: 'Fügen Sie mehr als 5 Benutzer hinzu, mit bis zu 10 Plätzen im Pro-Plan',
        es: 'Añade más de 5 usuarios, con hasta 10 plazas en Pro',
        it: 'Aggiungi più di 5 utenti, con fino a 10 posti nel piano Pro',
      },
    },
    {
      id: 'rbac',
      plan: 'enterprise',
      label: 'Role-based access control',
      label_localized: {
        de: 'Rollenbasierte Zugriffskontrolle',
        es: 'Control de acceso basado en roles',
        it: 'Controllo degli accessi basato sui ruoli',
      },
      description: 'Assign roles and granular permissions to each user account',
      description_localized: {
        de: 'Weisen Sie jedem Benutzerkonto Rollen und granulare Berechtigungen zu',
        es: 'Asigna roles y permisos granulares a cada cuenta de usuario',
        it: 'Assegna ruoli e permessi granulari a ciascun account utente',
      },
    },
    {
      id: 'backup_reports',
      plan: 'pro',
      label: 'Scheduled backup reports',
      label_localized: {
        de: 'Geplante Backup-Berichte',
        es: 'Informes programados de copias de seguridad',
        it: 'Report pianificati dei backup',
      },
      description:
        'Generate daily, weekly, and monthly backup summaries with status, size, and job insights',
      description_localized: {
        de: 'Erstellen Sie tägliche, wöchentliche und monatliche Backup-Zusammenfassungen mit Status-, Größen- und Job-Einblicken',
        es: 'Genera resúmenes diarios, semanales y mensuales de copias de seguridad con información sobre estado, tamaño y trabajos',
        it: 'Genera riepiloghi giornalieri, settimanali e mensili dei backup con informazioni su stato, dimensioni e attività',
      },
      available_in: '2.0.1',
    },
    {
      id: 'dashboard_analytics',
      plan: 'pro',
      label: 'Expanded dashboard analytics',
      label_localized: {
        de: 'Erweiterte Dashboard-Analysen',
        es: 'Analíticas ampliadas del panel',
        it: 'Analisi dashboard estese',
      },
      description:
        'Add more charts and trend views to the dashboard for backup health, activity, and storage monitoring',
      description_localized: {
        de: 'Mehr Diagramme und Trendansichten im Dashboard für Backup-Zustand, Aktivität und Speicherüberwachung',
        es: 'Añade más gráficos y vistas de tendencias al panel para supervisar el estado de las copias, la actividad y el almacenamiento',
        it: 'Aggiunge più grafici e viste dei trend alla dashboard per monitorare stato dei backup, attività e archiviazione',
      },
    },
    {
      id: 'database_discovery',
      plan: 'pro',
      label: 'Database scanning and setup',
      label_localized: {
        de: 'Datenbank-Scan und Einrichtung',
        es: 'Escaneo y configuración de bases de datos',
        it: 'Scansione e configurazione dei database',
      },
      description:
        'Scan the host for common databases and turn them into backup jobs with guided setup',
      description_localized: {
        de: 'Scannen Sie den Host nach gängigen Datenbanken und wandeln Sie sie mit geführter Einrichtung in Backup-Jobs um',
        es: 'Escanea el host en busca de bases de datos comunes y conviértelas en trabajos de copia de seguridad con una configuración guiada',
        it: "Analizza l'host alla ricerca di database comuni e trasformali in processi di backup con configurazione guidata",
      },
    },
    {
      id: 'container_backups',
      plan: 'pro',
      label: 'Container backup setup',
      label_localized: {
        de: 'Container-Backup-Einrichtung',
        es: 'Configuración de copias de seguridad de contenedores',
        it: 'Configurazione dei backup dei container',
      },
      description:
        'Make it easier to back up Docker containers and volumes, including Borg UI itself',
      description_localized: {
        de: 'Erleichtern Sie das Sichern von Docker-Containern und Volumes, einschließlich Borg UI selbst',
        es: 'Facilita la copia de seguridad de contenedores y volúmenes de Docker, incluida la propia Borg UI',
        it: 'Semplifica il backup di container e volumi Docker, inclusa la stessa Borg UI',
      },
    },
    {
      id: 'alerting_monitoring',
      plan: 'pro',
      label: 'Advanced alerts and monitoring',
      label_localized: {
        de: 'Erweiterte Warnmeldungen und Überwachung',
        es: 'Alertas y supervisión avanzadas',
        it: 'Avvisi e monitoraggio avanzati',
      },
      description:
        'Expand health checks, failure alerts, and monitoring views for production backup workflows',
      description_localized: {
        de: 'Erweitern Sie Health Checks, Fehlerwarnungen und Überwachungsansichten für produktive Backup-Workflows',
        es: 'Amplía las comprobaciones de estado, las alertas de fallos y las vistas de supervisión para flujos de trabajo de copias de seguridad en producción',
        it: 'Espandi controlli di integrità, avvisi di errore e viste di monitoraggio per i flussi di lavoro di backup in produzione',
      },
    },
    {
      id: 'multi_repo_orchestration',
      plan: 'pro',
      label: 'Multi-repository backups',
      label_localized: {
        de: 'Backups über mehrere Repositories',
        es: 'Copias de seguridad de varios repositorios',
        it: 'Backup multi-repository',
      },
      description: 'Manage and run backups across multiple repositories with less repetitive setup',
      description_localized: {
        de: 'Verwalten und starten Sie Backups über mehrere Repositories mit weniger repetitiver Einrichtung',
        es: 'Gestiona y ejecuta copias de seguridad en varios repositorios con una configuración menos repetitiva',
        it: 'Gestisci ed esegui backup su più repository con una configurazione meno ripetitiva',
      },
    },
    {
      id: 'multi_source_policies',
      plan: 'pro',
      label: 'Multi-source backups',
      label_localized: {
        de: 'Backups aus mehreren Quellen',
        es: 'Copias de seguridad de múltiples orígenes',
        it: 'Backup multi-sorgente',
      },
      description:
        'Back up multiple source locations in one job with cleaner scheduling and configuration',
      description_localized: {
        de: 'Sichern Sie mehrere Quellpfade in einem Auftrag mit übersichtlicherer Planung und Konfiguration',
        es: 'Haz copias de seguridad de varias ubicaciones de origen en un solo trabajo con una planificación y configuración más limpias',
        it: 'Esegui il backup di più posizioni sorgente in un unico processo con pianificazione e configurazione più ordinate',
      },
    },
    {
      id: 'rclone_destinations',
      plan: 'pro',
      label: 'Rclone destinations',
      label_localized: {
        de: 'Rclone-Ziele',
        es: 'Destinos de rclone',
        it: 'Destinazioni rclone',
      },
      description: 'Connect more cloud and remote storage targets through built-in rclone support',
      description_localized: {
        de: 'Verbinden Sie mehr Cloud- und Remote-Speicherziele über die integrierte rclone-Unterstützung',
        es: 'Conecta más destinos de almacenamiento en la nube y remotos mediante la compatibilidad integrada con rclone',
        it: 'Collega più destinazioni cloud e di archiviazione remota tramite il supporto rclone integrato',
      },
    },
    {
      id: 'compliance_exports',
      plan: 'enterprise',
      label: 'Audit and compliance exports',
      label_localized: {
        de: 'Audit- und Compliance-Exporte',
        es: 'Exportaciones de auditoría y cumplimiento',
        it: 'Esportazioni per audit e conformità',
      },
      description:
        'Export backup history, retention evidence, and operational records for reporting and reviews',
      description_localized: {
        de: 'Exportieren Sie Backup-Verlauf, Aufbewahrungsnachweise und Betriebsdaten für Berichte und Prüfungen',
        es: 'Exporta el historial de copias, las pruebas de retención y los registros operativos para informes y revisiones',
        it: 'Esporta cronologia dei backup, prove di conservazione e registri operativi per report e revisioni',
      },
    },
    {
      id: 'centralized_management',
      plan: 'enterprise',
      label: 'Centralized backup management',
      label_localized: {
        de: 'Zentrale Backup-Verwaltung',
        es: 'Gestión centralizada de copias de seguridad',
        it: 'Gestione centralizzata dei backup',
      },
      description:
        'Oversee larger backup environments with stronger controls and a more consolidated workflow',
      description_localized: {
        de: 'Überwachen Sie größere Backup-Umgebungen mit stärkeren Kontrollen und einem stärker gebündelten Workflow',
        es: 'Supervisa entornos de copias de seguridad más grandes con controles más sólidos y un flujo de trabajo más unificado',
        it: 'Supervisiona ambienti di backup più grandi con controlli più rigorosi e un flusso di lavoro più consolidato',
      },
    },
  ],
}

export function getPlanContentUrl() {
  const configuredUrl = import.meta.env.VITE_PLAN_CONTENT_URL?.trim()
  if (configuredUrl) return configuredUrl

  if (import.meta.env.DEV) return LOCAL_PLAN_CONTENT_URL

  return DEFAULT_REMOTE_PLAN_CONTENT_URL
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

function isLocalizedStringMap(value: unknown): value is Record<string, string> | undefined {
  return (
    value === undefined ||
    (typeof value === 'object' && value !== null && Object.values(value).every(isNonEmptyString))
  )
}

function isValidPlanContentFeature(feature: unknown): feature is PlanContentFeature {
  if (!feature || typeof feature !== 'object') return false

  const candidate = feature as Partial<PlanContentFeature>
  return (
    isNonEmptyString(candidate.id) &&
    (candidate.plan === 'community' ||
      candidate.plan === 'pro' ||
      candidate.plan === 'enterprise') &&
    isNonEmptyString(candidate.label) &&
    isLocalizedStringMap(candidate.label_localized) &&
    isNonEmptyString(candidate.description) &&
    isLocalizedStringMap(candidate.description_localized) &&
    (candidate.available_in === undefined || isNonEmptyString(candidate.available_in))
  )
}

export async function fetchPlanContentManifest(url = getPlanContentUrl()) {
  const response = await fetch(url, {
    headers: {
      Accept: 'application/json',
    },
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch plan content manifest (${response.status})`)
  }

  const data = (await response.json()) as Partial<PlanContentManifest>
  return {
    version:
      typeof data.version === 'number' ? data.version : DEFAULT_PLAN_CONTENT_MANIFEST.version,
    generated_at: data.generated_at,
    features: Array.isArray(data.features)
      ? data.features.filter(isValidPlanContentFeature)
      : DEFAULT_PLAN_CONTENT_MANIFEST.features,
  } satisfies PlanContentManifest
}
