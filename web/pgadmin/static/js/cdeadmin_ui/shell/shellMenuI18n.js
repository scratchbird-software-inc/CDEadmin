/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import gettext from 'sources/gettext';

/**
 * Internationalization (i18n) catalog and translation helpers for the
 * ScratchRobin Main Navigation Menu and Shell controls.
 *
 * Resolution priority for `translateShell(locale, key, defaultText, ...args)`:
 *   1. Runtime / locale-specific table entry for `locale` (or base language, e.g. `fr` for `fr_FR`).
 *   2. Flask-Babel `gettext(defaultText)` when the server catalog provides a non-identity translation.
 *   3. English (`en`) canonical catalog entry or `defaultText`.
 */

const SHELL_STRINGS = {
  en: {
    'shell.nav.aria': 'Main Menu',
    'shell.nav.utilities_aria': 'Language and Appearance',
    'shell.system.label': 'System Session Menu',
    'shell.system.hint': 'ScratchRobin Session (Lock Screen / Logout)',

    // Top-level menu triggers
    'menu.applications.title': 'Applications',
    'menu.window.title': 'Window',
    'menu.help.title': 'Help',
    'menu.object.title': 'Object',
    'menu.query.title': 'Query',
    'menu.model.title': 'Model',
    'menu.cube.title': 'Cube',
    'menu.bi.title': 'BI',
    'menu.screen_mesh.title': 'Screen Mesh',
    'menu.project.title': 'Project',

    // Applications menu (index 60)
    'menu.applications.data_sources.text': 'Data Sources',
    'menu.applications.data_sources.hint':
      'Configure database servers, engines, and connection profiles.',
    'menu.applications.database_engines.text': 'Database Engines (On / Off)',
    'menu.applications.database_engines.hint':
      'Enable or disable PostgreSQL, Firebird, DuckDB, SQLite, MariaDB, ScratchBird, and other engines.',
    'menu.applications.security.text': 'Security, Users & Groups',
    'menu.applications.security.hint':
      'Turn workspace applications ON/OFF, manage users & groups, and grant or revoke permissions.',
    'menu.applications.menus_toolbars.text': 'Menus, Toolbars & Icons',
    'menu.applications.menus_toolbars.hint':
      'Place action icons onto global menus, application menus, and tabbed-notebook-iconbars.',
    'menu.applications.schemes_fonts.text': 'Colour Schemes & Fonts',
    'menu.applications.schemes_fonts.hint':
      'Select or build custom colour schemes and customize UI, SQL, and diagram fonts.',
    'menu.applications.preferences.text': 'Preferences',
    'menu.applications.preferences.hint':
      'Personalize colors, typography, shortcuts, and user API keys.',
    'menu.applications.launch_hint': 'Open a new %s workspace instance.',

    // Canonical application labels & descriptions
    'app.data-navigator.label': 'Data Navigator',
    'app.data-navigator.hint':
      'Browse multi-engine servers, databases, schemas, tables, and views.',
    'app.sql-editor.label': 'SQL Editor',
    'app.sql-editor.hint':
      'Author, execute, and inspect queries in an isolated SQL session.',
    'app.erd-designer.label': 'ERD & Data Modelling',
    'app.erd-designer.hint':
      'Design conceptual, logical, physical, and deployment DDN models.',
    'app.cube-designer.label': 'Cube Designer',
    'app.cube-designer.hint':
      'Model dimensions, hierarchies, measures, and aggregate plans.',
    'app.bi-designer.label': 'BI Questions & Dashboards',
    'app.bi-designer.hint':
      'Build governed questions, charts, and interactive DDN dashboards.',
    'app.screen-mesh-designer.label': 'Screen Mesh Designer',
    'app.screen-mesh-designer.hint':
      'Create data-bound screen wireframes, regions, and navigation flows.',
    'app.schema-compare.label': 'Schema Comparison',
    'app.schema-compare.hint':
      'Compare live catalogs, baselines, and DDN designs to review diffs.',
    'app.project-explorer.label': 'Project Explorer',
    'app.project-explorer.hint':
      'Manage versioned project assets, notebooks, and Git snapshots.',
    'app.command-line.label': 'Command Line',
    'app.command-line.hint':
      'Launch an interactive database shell session.',

    // Window menu (index 70)
    'menu.window.tabbed_icon_bar.text': 'Tabbed-Icon-Bar',
    'menu.window.tabbed_icon_bar.hint':
      'Show or hide the focused application ribbon bar on the Main Form.',
    'menu.window.status_bar.text': 'Status Bar',
    'menu.window.status_bar.hint':
      'Show or hide the bottom status bar on active work areas.',
    'menu.window.left_drawer.text': 'Left Side Drawer',
    'menu.window.left_drawer.hint':
      'Toggle the active application navigation drawer on the left.',
    'menu.window.right_drawer.text': 'Right Side Drawer',
    'menu.window.right_drawer.hint':
      'Toggle the active application inspector drawer on the right.',
    'menu.window.user_dashboard.text': 'User Dashboard',
    'menu.window.user_dashboard.hint':
      'Open or focus the ScratchRobin User Dashboard.',
    'menu.window.close.text': 'Close',
    'menu.window.close.hint': 'Close the currently focused application.',
    'menu.window.open_app_floating_suffix': '(Floating)',
    'menu.window.focus_instance.hint': 'Switch focus to %s.',

    // Help menu (index 80)
    'menu.help.sql_reference.text': 'SQL Reference',
    'menu.help.sql_reference.hint':
      'Syntax and dialect reference across supported SQL engines.',
    'menu.help.engine_reference.text': 'Database Engine Reference',
    'menu.help.engine_reference.hint':
      'Capabilities, native types, and operational notes by engine.',
    'menu.help.glossary.text': 'Glossary of Terms',
    'menu.help.glossary.hint':
      'Definitions of ScratchRobin, CDE, DDN, and data-modelling terms.',
    'menu.help.docs.text': 'Help',
    'menu.help.docs.hint': 'Open ScratchRobin user documentation and guides.',
    'menu.help.about.text': 'About',
    'menu.help.about.hint': 'Version, build provenance, and license details.',

    // Focused-application dynamic items
    'menu.object.refresh_catalog.text': 'Refresh Catalog',
    'menu.object.refresh_catalog.hint':
      'Reload metadata for the selected server, database, or schema branch.',
    'menu.query.execute_sql.text': 'Execute SQL',
    'menu.query.execute_sql.hint':
      'Run the active SQL statement or selection.',
    'menu.model.new_model.text': 'New Data Model',
    'menu.model.new_model.hint':
      'Create a new Draft DDN conceptual, logical, or physical model.',
    'menu.cube.new_cube.text': 'New Cube',
    'menu.cube.new_cube.hint':
      'Create a new Draft dimensional DDN cube design.',
    'menu.bi.new_design.text': 'New BI Design',
    'menu.bi.new_design.hint':
      'Create a new Draft BI question or DDN dashboard.',
    'menu.screen_mesh.new_mesh.text': 'New Screen Mesh',
    'menu.screen_mesh.new_mesh.hint':
      'Create a new Draft data-bound screen wireframe or flow.',
    'menu.project.new_project.text': 'New Project',
    'menu.project.new_project.hint':
      'Create a new versioned ScratchRobin project workspace.',

    // Right-aligned Language & Tone controls
    'shell.language.aria': 'Language (%s)',
    'shell.language.hint': 'Switch interface language',
    'shell.language.heading': 'Interface Language',
    'shell.tone.dark': 'Dark',
    'shell.tone.light': 'Light',
    'shell.tone.switch_to_dark': 'Switch to dark theme',
    'shell.tone.switch_to_light': 'Switch to light theme',

    // Area 2 — Vertical Dock Side Menu
    'shell.side.nav_aria': 'Side Menu Application Launcher',
    'shell.side.launch_aria': 'Launch Applications',
    'shell.side.left_drawer_toggle': 'Toggle Left Side Drawer',
    'shell.side.left_drawer_unavailable': 'Left Side Drawer (Unavailable)',
    'shell.side.open_app': 'Open %s',
    'shell.side.settings': 'Settings',
    'shell.side.settings_options': 'Settings Options',
    'shell.side.app_settings': 'Application Settings',
    'shell.side.global_settings': 'Global Settings',
  },

  fr: {
    'shell.nav.aria': 'Menu principal',
    'shell.nav.utilities_aria': 'Langue et apparence',
    'shell.system.label': 'Menu de session système',
    'shell.system.hint': 'Session ScratchRobin (Verrouiller / Déconnexion)',
    'menu.applications.title': 'Applications',
    'menu.window.title': 'Fenêtre',
    'menu.help.title': 'Aide',
    'menu.object.title': 'Objet',
    'menu.query.title': 'Requête',
    'menu.model.title': 'Modèle',
    'menu.cube.title': 'Cube',
    'menu.bi.title': 'BI',
    'menu.screen_mesh.title': 'Maillage écran',
    'menu.project.title': 'Projet',
    'menu.applications.data_sources.text': 'Sources de données',
    'menu.applications.data_sources.hint':
      'Configurer les serveurs, moteurs et profils de connexion.',
    'menu.applications.preferences.text': 'Préférences',
    'menu.applications.preferences.hint':
      'Personnaliser les couleurs, polices, raccourcis et clés API.',
    'menu.applications.launch_hint': 'Ouvrir une nouvelle instance de %s.',
    'app.data-navigator.label': 'Navigateur de données',
    'app.data-navigator.hint':
      'Parcourir les serveurs, bases, schémas, tables et vues multi-moteurs.',
    'app.sql-editor.label': 'Éditeur SQL',
    'app.sql-editor.hint':
      'Rédiger, exécuter et inspecter des requêtes SQL isolées.',
    'app.erd-designer.label': 'Modélisation & ERD',
    'app.erd-designer.hint':
      'Concevoir des modèles DDN conceptuels, logiques et physiques.',
    'app.cube-designer.label': 'Concepteur de cubes',
    'app.cube-designer.hint':
      'Modéliser dimensions, mesures et plans d’agrégation.',
    'app.bi-designer.label': 'Questions & Tableaux BI',
    'app.bi-designer.hint':
      'Créer des questions gouvernées et tableaux de bord DDN.',
    'app.screen-mesh-designer.label': 'Maillage d’écrans',
    'app.screen-mesh-designer.hint':
      'Concevoir des maquettes filaires liées aux données.',
    'app.schema-compare.label': 'Comparaison de schémas',
    'app.schema-compare.hint':
      'Comparer catalogues actifs, versions de base et modèles DDN.',
    'app.project-explorer.label': 'Explorateur de projets',
    'app.project-explorer.hint':
      'Gérer les ressources versionnées et instantanés Git.',
    'app.command-line.label': 'Ligne de commande',
    'app.command-line.hint': 'Ouvrir un terminal interactif de base de données.',
    'menu.window.tabbed_icon_bar.text': 'Barre d’icônes à onglets',
    'menu.window.tabbed_icon_bar.hint':
      'Afficher ou masquer la barre ruban de l’application active.',
    'menu.window.status_bar.text': 'Barre d’état',
    'menu.window.status_bar.hint':
      'Afficher ou masquer la barre d’état inférieure.',
    'menu.window.left_drawer.text': 'Tiroir latéral gauche',
    'menu.window.left_drawer.hint':
      'Afficher ou masquer le tiroir de navigation gauche.',
    'menu.window.right_drawer.text': 'Tiroir latéral droit',
    'menu.window.right_drawer.hint':
      'Afficher ou masquer le tiroir d’inspection droit.',
    'menu.window.user_dashboard.text': 'Tableau de bord utilisateur',
    'menu.window.user_dashboard.hint':
      'Ouvrir ou activer le tableau de bord utilisateur.',
    'menu.window.close.text': 'Fermer',
    'menu.window.close.hint': 'Fermer l’application active.',
    'menu.window.open_app_floating_suffix': '(Flottante)',
    'menu.window.focus_instance.hint': 'Basculer vers %s.',
    'menu.help.sql_reference.text': 'Référence SQL',
    'menu.help.sql_reference.hint':
      'Syntaxe et dialectes SQL des moteurs pris en charge.',
    'menu.help.engine_reference.text': 'Référence des moteurs',
    'menu.help.engine_reference.hint':
      'Capacités, types natifs et notes par moteur de base de données.',
    'menu.help.glossary.text': 'Glossaire des termes',
    'menu.help.glossary.hint':
      'Définitions des termes ScratchRobin, CDE et DDN.',
    'menu.help.docs.text': 'Aide',
    'menu.help.docs.hint': 'Ouvrir la documentation utilisateur ScratchRobin.',
    'menu.help.about.text': 'À propos',
    'menu.help.about.hint': 'Version, provenance et licence.',
    'menu.object.refresh_catalog.text': 'Actualiser le catalogue',
    'menu.object.refresh_catalog.hint':
      'Recharger les métadonnées de la branche sélectionnée.',
    'menu.query.execute_sql.text': 'Exécuter SQL',
    'menu.query.execute_sql.hint': 'Exécuter la requête SQL active.',
    'menu.model.new_model.text': 'Nouveau modèle de données',
    'menu.model.new_model.hint': 'Créer un brouillon de modèle DDN.',
    'menu.cube.new_cube.text': 'Nouveau cube',
    'menu.cube.new_cube.hint': 'Créer un brouillon de cube dimensionnel DDN.',
    'menu.bi.new_design.text': 'Nouvelle conception BI',
    'menu.bi.new_design.hint': 'Créer une question ou un tableau de bord BI.',
    'menu.screen_mesh.new_mesh.text': 'Nouveau maillage d’écran',
    'menu.screen_mesh.new_mesh.hint': 'Créer une maquette filaire liée aux données.',
    'menu.project.new_project.text': 'Nouveau projet',
    'menu.project.new_project.hint': 'Créer un espace de projet versionné.',
    'shell.language.aria': 'Langue (%s)',
    'shell.language.hint': 'Changer la langue de l’interface',
    'shell.language.heading': 'Langue de l’interface',
    'shell.tone.dark': 'Sombre',
    'shell.tone.light': 'Clair',
    'shell.tone.switch_to_dark': 'Passer au thème sombre',
    'shell.tone.switch_to_light': 'Passer au thème clair',
    'shell.side.nav_aria': 'Lanceur d’applications latéral',
    'shell.side.launch_aria': 'Lancer des applications',
    'shell.side.left_drawer_toggle': 'Basculer le tiroir gauche',
    'shell.side.left_drawer_unavailable': 'Tiroir gauche (indisponible)',
    'shell.side.open_app': 'Ouvrir %s',
    'shell.side.settings': 'Paramètres',
    'shell.side.settings_options': 'Options des paramètres',
    'shell.side.app_settings': 'Paramètres de l’application',
    'shell.side.global_settings': 'Paramètres globaux',
  },

  de: {
    'shell.nav.aria': 'Hauptmenü',
    'shell.nav.utilities_aria': 'Sprache und Darstellung',
    'shell.system.label': 'System-Sitzungsmenü',
    'shell.system.hint': 'ScratchRobin-Sitzung (Bildschirm sperren / Abmelden)',
    'menu.applications.title': 'Anwendungen',
    'menu.window.title': 'Fenster',
    'menu.help.title': 'Hilfe',
    'menu.object.title': 'Objekt',
    'menu.query.title': 'Abfrage',
    'menu.model.title': 'Modell',
    'menu.cube.title': 'Cube',
    'menu.bi.title': 'BI',
    'menu.screen_mesh.title': 'Maskennetz',
    'menu.project.title': 'Projekt',
    'menu.applications.data_sources.text': 'Datenquellen',
    'menu.applications.data_sources.hint':
      'Datenbankserver, Engines und Verbindungsprofile verwalten.',
    'menu.applications.preferences.text': 'Benutzereinstellungen',
    'menu.applications.preferences.hint':
      'Farben, Schriftarten, Tastenkürzel und API-Schlüssel anpassen.',
    'menu.applications.launch_hint': 'Neue Instanz von %s öffnen.',
    'app.data-navigator.label': 'Daten-Navigator',
    'app.data-navigator.hint':
      'Server, Datenbanken, Schemata, Tabellen und Sichten durchsuchen.',
    'app.sql-editor.label': 'SQL-Editor',
    'app.sql-editor.hint':
      'SQL-Abfragen in einer isolierten Sitzung bearbeiten und ausführen.',
    'app.erd-designer.label': 'ERD & Datenmodellierung',
    'app.erd-designer.hint':
      'Konzeptionelle, logische und physische DDN-Modelle entwerfen.',
    'app.cube-designer.label': 'Cube-Designer',
    'app.cube-designer.hint':
      'Dimensionen, Kennzahlen und Aggregationspläne modellieren.',
    'app.bi-designer.label': 'BI-Fragen & Dashboards',
    'app.bi-designer.hint':
      'Gesteuerte Abfragen, Diagramme und DDN-Dashboards erstellen.',
    'app.screen-mesh-designer.label': 'Screen-Mesh-Designer',
    'app.screen-mesh-designer.hint':
      'Datengebundene Drahtgittermodelle und Maskenflüsse entwerfen.',
    'app.schema-compare.label': 'Schemavergleich',
    'app.schema-compare.hint':
      'Live-Kataloge und DDN-Entwürfe vergleichen.',
    'app.project-explorer.label': 'Projekt-Explorer',
    'app.project-explorer.hint':
      'Versionierte Projektdateien und Git-Stände verwalten.',
    'app.command-line.label': 'Befehlszeile',
    'app.command-line.hint': 'Interaktive Datenbank-Shell starten.',
    'menu.window.tabbed_icon_bar.text': 'Register-Symbolleiste',
    'menu.window.tabbed_icon_bar.hint':
      'Symbolleiste der aktiven Anwendung ein- oder ausblenden.',
    'menu.window.status_bar.text': 'Statusleiste',
    'menu.window.status_bar.hint':
      'Untere Statusleiste im Arbeitsbereich ein- oder ausblenden.',
    'menu.window.left_drawer.text': 'Linker Seitenbereich',
    'menu.window.left_drawer.hint':
      'Linken Navigationsbereich der aktiven Anwendung umschalten.',
    'menu.window.right_drawer.text': 'Rechter Seitenbereich',
    'menu.window.right_drawer.hint':
      'Rechten Inspektionsbereich der aktiven Anwendung umschalten.',
    'menu.window.user_dashboard.text': 'Benutzer-Dashboard',
    'menu.window.user_dashboard.hint':
      'ScratchRobin-Benutzer-Dashboard öffnen oder fokussieren.',
    'menu.window.close.text': 'Schließen',
    'menu.window.close.hint': 'Aktive Anwendung schließen.',
    'menu.window.open_app_floating_suffix': '(Freischwebend)',
    'menu.window.focus_instance.hint': 'Fokus auf %s wechseln.',
    'menu.help.sql_reference.text': 'SQL-Referenz',
    'menu.help.sql_reference.hint':
      'SQL-Syntax- und Dialektreferenz der unterstützten Engines.',
    'menu.help.engine_reference.text': 'Datenbank-Engine-Referenz',
    'menu.help.engine_reference.hint':
      'Funktionen, native Datentypen und Hinweise je Engine.',
    'menu.help.glossary.text': 'Glossar',
    'menu.help.glossary.hint':
      'Begriffsdefinitionen zu ScratchRobin, CDE und DDN.',
    'menu.help.docs.text': 'Hilfe',
    'menu.help.docs.hint': 'ScratchRobin-Benutzerhandbuch öffnen.',
    'menu.help.about.text': 'Über ScratchRobin',
    'menu.help.about.hint': 'Versions-, Build- und Lizenzinformationen.',
    'menu.object.refresh_catalog.text': 'Katalog aktualisieren',
    'menu.object.refresh_catalog.hint':
      'Metadaten des ausgewählten Zweigs neu laden.',
    'menu.query.execute_sql.text': 'SQL ausführen',
    'menu.query.execute_sql.hint': 'Aktive SQL-Anweisung ausführen.',
    'menu.model.new_model.text': 'Neues Datenmodell',
    'menu.model.new_model.hint': 'Neuen DDN-Datenmodell-Entwurf anlegen.',
    'menu.cube.new_cube.text': 'Neuer Cube',
    'menu.cube.new_cube.hint': 'Neuen dimensionalen DDN-Cube-Entwurf anlegen.',
    'menu.bi.new_design.text': 'Neuer BI-Entwurf',
    'menu.bi.new_design.hint': 'Neue BI-Frage oder neues Dashboard anlegen.',
    'menu.screen_mesh.new_mesh.text': 'Neues Screen-Mesh',
    'menu.screen_mesh.new_mesh.hint': 'Neues datengebundenes Drahtgittermodell anlegen.',
    'menu.project.new_project.text': 'Neues Projekt',
    'menu.project.new_project.hint': 'Neuen versionierten Projektbereich erstellen.',
    'shell.language.aria': 'Sprache (%s)',
    'shell.language.hint': 'Oberflächensprache wechseln',
    'shell.language.heading': 'Oberflächensprache',
    'shell.tone.dark': 'Dunkel',
    'shell.tone.light': 'Hell',
    'shell.tone.switch_to_dark': 'Zum dunklen Design wechseln',
    'shell.tone.switch_to_light': 'Zum hellen Design wechseln',
    'shell.side.nav_aria': 'Seitenmenü-Anwendungsstarter',
    'shell.side.launch_aria': 'Anwendungen starten',
    'shell.side.left_drawer_toggle': 'Linken Seitenbereich umschalten',
    'shell.side.left_drawer_unavailable': 'Linker Seitenbereich (nicht verfügbar)',
    'shell.side.open_app': '%s öffnen',
    'shell.side.settings': 'Einstellungen',
    'shell.side.settings_options': 'Einstellungsoptionen',
    'shell.side.app_settings': 'Anwendungseinstellungen',
    'shell.side.global_settings': 'Globale Einstellungen',
  },

  es: {
    'shell.nav.aria': 'Menú principal',
    'shell.nav.utilities_aria': 'Idioma y apariencia',
    'shell.system.label': 'Menú de sesión del sistema',
    'shell.system.hint': 'Sesión de ScratchRobin (Bloquear pantalla / Cerrar sesión)',
    'menu.applications.title': 'Aplicaciones',
    'menu.window.title': 'Ventana',
    'menu.help.title': 'Ayuda',
    'menu.object.title': 'Objeto',
    'menu.query.title': 'Consulta',
    'menu.model.title': 'Modelo',
    'menu.cube.title': 'Cubo',
    'menu.bi.title': 'BI',
    'menu.screen_mesh.title': 'Malla de pantalla',
    'menu.project.title': 'Proyecto',
    'menu.applications.data_sources.text': 'Orígenes de datos',
    'menu.applications.data_sources.hint':
      'Configurar servidores, motores y perfiles de conexión.',
    'menu.applications.preferences.text': 'Preferencias',
    'menu.applications.preferences.hint':
      'Personalizar colores, fuentes, atajos y claves API.',
    'menu.applications.launch_hint': 'Abrir una nueva instancia de %s.',
    'app.data-navigator.label': 'Navegador de datos',
    'app.data-navigator.hint':
      'Explorar servidores, bases de datos, esquemas, tablas y vistas.',
    'app.sql-editor.label': 'Editor SQL',
    'app.sql-editor.hint':
      'Escribir, ejecutar e inspeccionar consultas SQL aisladas.',
    'app.erd-designer.label': 'ERD y Modelado de datos',
    'app.erd-designer.hint':
      'Diseñar modelos DDN conceptuales, lógicos y físicos.',
    'app.cube-designer.label': 'Diseñador de cubos',
    'app.cube-designer.hint':
      'Modelar dimensiones, medidas y planes de agregación.',
    'app.bi-designer.label': 'Preguntas y Paneles BI',
    'app.bi-designer.hint':
      'Crear preguntas gobernadas y paneles interactivos DDN.',
    'app.screen-mesh-designer.label': 'Diseñador de mallas',
    'app.screen-mesh-designer.hint':
      'Crear esquemas de pantallas vinculados a datos.',
    'app.schema-compare.label': 'Comparación de esquemas',
    'app.schema-compare.hint':
      'Comparar catálogos activos y diseños DDN.',
    'app.project-explorer.label': 'Explorador de proyectos',
    'app.project-explorer.hint':
      'Gestionar recursos versionados e instantáneas Git.',
    'app.command-line.label': 'Línea de comandos',
    'app.command-line.hint': 'Iniciar consola interactiva de base de datos.',
    'menu.window.tabbed_icon_bar.text': 'Barra de iconos con pestañas',
    'menu.window.tabbed_icon_bar.hint':
      'Mostrar u ocultar la barra de herramientas con pestañas.',
    'menu.window.status_bar.text': 'Barra de estado',
    'menu.window.status_bar.hint':
      'Mostrar u ocultar la barra de estado inferior.',
    'menu.window.left_drawer.text': 'Panel lateral izquierdo',
    'menu.window.left_drawer.hint':
      'Alternar el panel de navegación izquierdo.',
    'menu.window.right_drawer.text': 'Panel lateral derecho',
    'menu.window.right_drawer.hint':
      'Alternar el panel inspector derecho.',
    'menu.window.user_dashboard.text': 'Panel de usuario',
    'menu.window.user_dashboard.hint':
      'Abrir o enfocar el panel principal del usuario.',
    'menu.window.close.text': 'Cerrar',
    'menu.window.close.hint': 'Cerrar la aplicación activa.',
    'menu.window.open_app_floating_suffix': '(Flotante)',
    'menu.window.focus_instance.hint': 'Cambiar el foco a %s.',
    'menu.help.sql_reference.text': 'Referencia SQL',
    'menu.help.sql_reference.hint':
      'Sintaxis y dialectos SQL de los motores compatibles.',
    'menu.help.engine_reference.text': 'Referencia de motores',
    'menu.help.engine_reference.hint':
      'Capacidades, tipos nativos y notas por motor.',
    'menu.help.glossary.text': 'Glosario de términos',
    'menu.help.glossary.hint':
      'Definiciones de términos de ScratchRobin, CDE y DDN.',
    'menu.help.docs.text': 'Ayuda',
    'menu.help.docs.hint': 'Abrir la documentación de ScratchRobin.',
    'menu.help.about.text': 'Acerca de',
    'menu.help.about.hint': 'Información de versión y licencia.',
    'menu.object.refresh_catalog.text': 'Actualizar catálogo',
    'menu.object.refresh_catalog.hint':
      'Recargar metadatos de la rama seleccionada.',
    'menu.query.execute_sql.text': 'Ejecutar SQL',
    'menu.query.execute_sql.hint': 'Ejecutar la instrucción SQL activa.',
    'menu.model.new_model.text': 'Nuevo modelo de datos',
    'menu.model.new_model.hint': 'Crear un nuevo borrador de modelo DDN.',
    'menu.cube.new_cube.text': 'Nuevo cubo',
    'menu.cube.new_cube.hint': 'Crear un nuevo borrador de cubo dimensional DDN.',
    'menu.bi.new_design.text': 'Nuevo diseño BI',
    'menu.bi.new_design.hint': 'Crear una nueva pregunta o panel BI.',
    'menu.screen_mesh.new_mesh.text': 'Nueva malla de pantalla',
    'menu.screen_mesh.new_mesh.hint': 'Crear un esquema de pantalla vinculado a datos.',
    'menu.project.new_project.text': 'Nuevo proyecto',
    'menu.project.new_project.hint': 'Crear un nuevo proyecto versionado.',
    'shell.language.aria': 'Idioma (%s)',
    'shell.language.hint': 'Cambiar idioma de la interfaz',
    'shell.language.heading': 'Idioma de la interfaz',
    'shell.tone.dark': 'Oscuro',
    'shell.tone.light': 'Claro',
    'shell.tone.switch_to_dark': 'Cambiar al tema oscuro',
    'shell.tone.switch_to_light': 'Cambiar al tema claro',
    'shell.side.nav_aria': 'Lanzador lateral de aplicaciones',
    'shell.side.launch_aria': 'Abrir aplicaciones',
    'shell.side.left_drawer_toggle': 'Alternar panel lateral izquierdo',
    'shell.side.left_drawer_unavailable': 'Panel izquierdo (no disponible)',
    'shell.side.open_app': 'Abrir %s',
    'shell.side.settings': 'Configuración',
    'shell.side.settings_options': 'Opciones de configuración',
    'shell.side.app_settings': 'Configuración de la aplicación',
    'shell.side.global_settings': 'Configuración global',
  },

  ja: {
    'shell.nav.aria': 'メインメニュー',
    'shell.nav.utilities_aria': '言語と外観',
    'shell.system.label': 'システムセッションメニュー',
    'shell.system.hint': 'ScratchRobin セッション（画面ロック / ログアウト）',
    'menu.applications.title': 'アプリケーション',
    'menu.window.title': 'ウィンドウ',
    'menu.help.title': 'ヘルプ',
    'menu.object.title': 'オブジェクト',
    'menu.query.title': 'クエリ',
    'menu.model.title': 'モデル',
    'menu.cube.title': 'キューブ',
    'menu.bi.title': 'BI',
    'menu.screen_mesh.title': 'スクリーンメッシュ',
    'menu.project.title': 'プロジェクト',
    'menu.applications.data_sources.text': 'データソース',
    'menu.applications.data_sources.hint':
      'データベースサーバー、エンジン、接続プロファイルを設定します。',
    'menu.applications.preferences.text': '環境設定',
    'menu.applications.preferences.hint':
      '配色、フォント、ショートカット、個人用 API キーを設定します。',
    'menu.applications.launch_hint': '%s の新しいワークスペースを開きます。',
    'app.data-navigator.label': 'データナビゲーター',
    'app.data-navigator.hint':
      'マルチエンジンのサーバー、データベース、スキーマ、テーブルを参照します。',
    'app.sql-editor.label': 'SQL エディター',
    'app.sql-editor.hint':
      '独立したセッションで SQL クエリを作成・実行します。',
    'app.erd-designer.label': 'ERD・データモデリング',
    'app.erd-designer.hint':
      '概念・論理・物理・配置の 4 階層 DDN モデルを設計します。',
    'app.cube-designer.label': 'キューブデザイナー',
    'app.cube-designer.hint':
      'ディメンション、メジャー、集計プランを設計します。',
    'app.bi-designer.label': 'BI 質問 & ダッシュボード',
    'app.bi-designer.hint':
      'ガバナンス対応の質問と DDN ダッシュボードを構築します。',
    'app.screen-mesh-designer.label': 'スクリーンメッシュデザイナー',
    'app.screen-mesh-designer.hint':
      'データ連携ワイヤーフレームと画面遷移を設計します。',
    'app.schema-compare.label': 'スキーマ比較',
    'app.schema-compare.hint':
      'ライブカタログと DDN 設計の差分を比較・検証します。',
    'app.project-explorer.label': 'プロジェクトエクスプローラー',
    'app.project-explorer.hint':
      'バージョン管理されたアセットと Git スナップショットを管理します。',
    'app.command-line.label': 'コマンドライン',
    'app.command-line.hint': '対話型データベースシェルを起動します。',
    'menu.window.tabbed_icon_bar.text': 'タブ付きアイコンバー',
    'menu.window.tabbed_icon_bar.hint':
      'メインフォームのタブ付きツールバーを表示または非表示にします。',
    'menu.window.status_bar.text': 'ステータスバー',
    'menu.window.status_bar.hint':
      '作業領域下部のステータスバーを表示または非表示にします。',
    'menu.window.left_drawer.text': '左サイドドロワー',
    'menu.window.left_drawer.hint':
      'アクティブなアプリケーションの左ナビゲーションを切り替えます。',
    'menu.window.right_drawer.text': '右サイドドロワー',
    'menu.window.right_drawer.hint':
      'アクティブなアプリケーションの右インスペクターを切り替えます。',
    'menu.window.user_dashboard.text': 'ユーザーダッシュボード',
    'menu.window.user_dashboard.hint':
      'ScratchRobin ユーザーダッシュボードを表示します。',
    'menu.window.close.text': '閉じる',
    'menu.window.close.hint': '現在フォーカスされているアプリケーションを閉じます。',
    'menu.window.open_app_floating_suffix': '（フローティング）',
    'menu.window.focus_instance.hint': '%s にフォーカスを切り替えます。',
    'menu.help.sql_reference.text': 'SQL リファレンス',
    'menu.help.sql_reference.hint': '対応エンジンの SQL 構文・方言リファレンス。',
    'menu.help.engine_reference.text': 'データベースエンジンリファレンス',
    'menu.help.engine_reference.hint': '各エンジンの機能・データ型・運用ガイド。',
    'menu.help.glossary.text': '用語集',
    'menu.help.glossary.hint': 'ScratchRobin・CDE・DDN の用語解説。',
    'menu.help.docs.text': 'ヘルプ',
    'menu.help.docs.hint': 'ScratchRobin ドキュメントを開きます。',
    'menu.help.about.text': 'バージョン情報',
    'menu.help.about.hint': 'バージョン、ビルド履歴、ライセンス情報。',
    'menu.object.refresh_catalog.text': 'カタログを更新',
    'menu.object.refresh_catalog.hint': '選択したブランチのメタデータを再読み込みします。',
    'menu.query.execute_sql.text': 'SQL を実行',
    'menu.query.execute_sql.hint': 'アクティブな SQL 文を実行します。',
    'menu.model.new_model.text': '新規データモデル',
    'menu.model.new_model.hint': '新しい DDN データモデルのドラフトを作成します。',
    'menu.cube.new_cube.text': '新規キューブ',
    'menu.cube.new_cube.hint': '新しい多次元 DDN キューブを作成します。',
    'menu.bi.new_design.text': '新規 BI デザイン',
    'menu.bi.new_design.hint': '新しい BI 質問またはダッシュボードを作成します。',
    'menu.screen_mesh.new_mesh.text': '新規スクリーンメッシュ',
    'menu.screen_mesh.new_mesh.hint': 'データ連携ワイヤーフレームを新規作成します。',
    'menu.project.new_project.text': '新規プロジェクト',
    'menu.project.new_project.hint': 'バージョン管理されたプロジェクトを作成します。',
    'shell.language.aria': '言語 (%s)',
    'shell.language.hint': 'インターフェース言語を切り替え',
    'shell.language.heading': 'インターフェース言語',
    'shell.tone.dark': 'ダーク',
    'shell.tone.light': 'ライト',
    'shell.tone.switch_to_dark': 'ダークテーマに切り替え',
    'shell.tone.switch_to_light': 'ライトテーマに切り替え',
    'shell.side.nav_aria': 'サイドメニュー・アプリケーションランチャー',
    'shell.side.launch_aria': 'アプリケーションを起動',
    'shell.side.left_drawer_toggle': '左サイドドロワーを切り替え',
    'shell.side.left_drawer_unavailable': '左サイドドロワー（利用不可）',
    'shell.side.open_app': '%s を開く',
    'shell.side.settings': '設定',
    'shell.side.settings_options': '設定オプション',
    'shell.side.app_settings': 'アプリケーション設定',
    'shell.side.global_settings': 'グローバル設定',
  },
};

const MENU_NAME_TO_I18N_KEY = Object.freeze({
  applications: 'menu.applications.title',
  window: 'menu.window.title',
  help: 'menu.help.title',
  object: 'menu.object.title',
  query: 'menu.query.title',
  model: 'menu.model.title',
  cube: 'menu.cube.title',
  bi: 'menu.bi.title',
  screen_mesh: 'menu.screen_mesh.title',
  project: 'menu.project.title',
});

function interpolate(template, args) {
  if (!args || args.length === 0) return template;
  let idx = 0;
  return String(template).replace(/%s/g, () =>
    idx < args.length ? String(args[idx++]) : '%s'
  );
}

export function normalizeShellLocale(locale) {
  const raw = String(locale || 'en').trim();
  if (!raw) return 'en';
  if (SHELL_STRINGS[raw]) return raw;
  const hyphenToUnderscore = raw.replace(/-/g, '_');
  if (SHELL_STRINGS[hyphenToUnderscore]) return hyphenToUnderscore;
  const base = hyphenToUnderscore.split('_')[0].toLowerCase();
  if (SHELL_STRINGS[base]) return base;
  return hyphenToUnderscore;
}

/**
 * Register or extend shell menu translations for a locale at runtime.
 */
export function registerShellLocaleStrings(locale, entries) {
  const norm = String(locale || '').trim();
  if (!norm || !entries || typeof entries !== 'object') return;
  SHELL_STRINGS[norm] = {
    ...(SHELL_STRINGS[norm] || {}),
    ...entries,
  };
}

/**
 * Translate a structured shell i18n key for `locale`, falling back to
 * `sources/gettext(defaultText)` and English defaults.
 */
export function translateShell(locale, key, defaultText = '', ...args) {
  const norm = normalizeShellLocale(locale);
  const base = norm.split('_')[0].toLowerCase();
  const enTable = SHELL_STRINGS.en;
  const targetTable = SHELL_STRINGS[norm] || SHELL_STRINGS[base];

  const fallback = defaultText || enTable[key] || key;

  if (norm !== 'en' && targetTable && targetTable[key]) {
    return interpolate(targetTable[key], args);
  }

  // Allow server-injected Flask-Babel catalog to translate when present
  if (typeof gettext === 'function' && fallback) {
    const serverTranslated = gettext(fallback, ...args);
    if (serverTranslated && serverTranslated !== fallback) {
      return serverTranslated;
    }
  }

  const chosen = (targetTable && targetTable[key]) || enTable[key] || fallback;
  return interpolate(chosen, args);
}

/**
 * Resolve a top-level menu trigger label through the i18n catalog.
 */
export function translateMenuTriggerLabel(locale, menu) {
  if (!menu) return '';
  if (menu.i18nKey) {
    return translateShell(locale, menu.i18nKey, menu.label || menu.name);
  }
  const mappedKey = MENU_NAME_TO_I18N_KEY[menu.name];
  if (mappedKey) {
    return translateShell(locale, mappedKey, menu.label || menu.name);
  }
  if (typeof gettext === 'function' && menu.label) {
    return gettext(menu.label);
  }
  return menu.label || menu.name;
}

const ITEM_ID_TO_I18N_PREFIX = Object.freeze({
  'shell.datasources.open': 'menu.applications.data_sources',
  'applications.data_sources': 'menu.applications.data_sources',
  'shell.preferences.open': 'menu.applications.preferences',
  'applications.preferences': 'menu.applications.preferences',
  'window.toolbar.notebookbar': 'menu.window.tabbed_icon_bar',
  'window.toggle.tabbed_icon_bar': 'menu.window.tabbed_icon_bar',
  'window.toolbar.status_bar': 'menu.window.status_bar',
  'window.toggle.status_bar': 'menu.window.status_bar',
  'shell.left_drawer.toggle': 'menu.window.left_drawer',
  'window.toggle.left_drawer': 'menu.window.left_drawer',
  'window.toolbar.right_drawer': 'menu.window.right_drawer',
  'shell.right_drawer.toggle': 'menu.window.right_drawer',
  'window.toggle.right_drawer': 'menu.window.right_drawer',
  'shell.window.dashboard': 'menu.window.user_dashboard',
  'window.user_dashboard': 'menu.window.user_dashboard',
  'shell.window.close': 'menu.window.close',
  'window.close_active': 'menu.window.close',
  'shell.help.sql_reference': 'menu.help.sql_reference',
  'help.sql_reference': 'menu.help.sql_reference',
  'shell.help.engine_reference': 'menu.help.engine_reference',
  'help.engine_reference': 'menu.help.engine_reference',
  'shell.help.glossary': 'menu.help.glossary',
  'help.glossary': 'menu.help.glossary',
  'shell.help.docs': 'menu.help.docs',
  'help.documentation': 'menu.help.docs',
  'shell.help.about': 'menu.help.about',
  'help.about': 'menu.help.about',
});

const CANONICAL_APP_IDS = Object.freeze([
  'data-navigator',
  'sql-editor',
  'erd-designer',
  'cube-designer',
  'bi-designer',
  'screen-mesh-designer',
  'schema-compare',
  'project-explorer',
  'command-line',
]);

/**
 * Resolve a menu item's display label through i18n keys, `t_actions`, and `gettext`.
 */
export function translateMenuItemLabel(locale, item, resolvedAction = null) {
  if (!item) return '';
  const args = Array.isArray(item.i18nArgs) ? item.i18nArgs : [];
  if (item.i18nKey) {
    return translateShell(
      locale,
      item.i18nKey,
      resolvedAction?.text || item.label || item.id,
      ...args
    );
  }
  const id = item.actionId || item.id || '';
  if (id.startsWith('shell.app.open.')) {
    const appId = id.slice('shell.app.open.'.length);
    return translateShell(
      locale,
      `app.${appId}.label`,
      resolvedAction?.text || item.label || appId
    );
  }
  const mappedPrefix = ITEM_ID_TO_I18N_PREFIX[id] || ITEM_ID_TO_I18N_PREFIX[item.id];
  if (mappedPrefix) {
    return translateShell(
      locale,
      `${mappedPrefix}.text`,
      resolvedAction?.text || item.label || id,
      ...args
    );
  }
  if (resolvedAction?.text) {
    return resolvedAction.text;
  }
  if (typeof gettext === 'function' && item.label) {
    return gettext(item.label);
  }
  return item.label || item.id || '';
}

/**
 * Resolve a menu item's subtitle / description hint through i18n keys and `t_actions`.
 */
export function translateMenuItemHint(locale, item, resolvedAction = null) {
  if (!item) return '';
  const args = Array.isArray(item.i18nArgs) ? item.i18nArgs : [];
  if (item.hintKey) {
    return translateShell(
      locale,
      item.hintKey,
      item.hint || resolvedAction?.hint || '',
      ...args
    );
  }
  const id = item.actionId || item.id || '';
  if (id.startsWith('shell.app.open.')) {
    const appId = id.slice('shell.app.open.'.length);
    return translateShell(
      locale,
      `app.${appId}.hint`,
      resolvedAction?.hint || ''
    );
  }
  const mappedPrefix = ITEM_ID_TO_I18N_PREFIX[id] || ITEM_ID_TO_I18N_PREFIX[item.id];
  if (mappedPrefix) {
    return translateShell(
      locale,
      `${mappedPrefix}.hint`,
      item.hint || resolvedAction?.hint || '',
      ...args
    );
  }
  if (item.hint) {
    return typeof gettext === 'function' ? gettext(item.hint) : item.hint;
  }
  return resolvedAction?.hint || '';
}

/**
 * Sync built-in shell action translations into a `TActionsRegistry` instance.
 */
export function syncShellActionStrings(actionsRegistry) {
  if (!actionsRegistry || typeof actionsRegistry.registerStrings !== 'function') {
    return;
  }

  Object.keys(SHELL_STRINGS).forEach((locale) => {
    const table = SHELL_STRINGS[locale];
    const bundle = {};
    if (table['shell.system.label']) {
      bundle['shell.system.session.text'] = table['shell.system.label'];
    }
    if (table['shell.system.hint']) {
      bundle['shell.system.session.hint'] = table['shell.system.hint'];
    }
    Object.entries(ITEM_ID_TO_I18N_PREFIX).forEach(([actionId, prefix]) => {
      if (table[`${prefix}.text`]) {
        bundle[`${actionId}.text`] = table[`${prefix}.text`];
      }
      if (table[`${prefix}.hint`]) {
        bundle[`${actionId}.hint`] = table[`${prefix}.hint`];
      }
    });
    CANONICAL_APP_IDS.forEach((appId) => {
      if (table[`app.${appId}.label`]) {
        bundle[`shell.app.open.${appId}.text`] = table[`app.${appId}.label`];
      }
      if (table[`app.${appId}.hint`]) {
        bundle[`shell.app.open.${appId}.hint`] = table[`app.${appId}.hint`];
      }
    });
    actionsRegistry.registerStrings(locale, bundle);
  });
}

export function getSupportedShellLocales() {
  return Object.keys(SHELL_STRINGS);
}
