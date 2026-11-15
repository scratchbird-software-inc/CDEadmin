/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

define(['translations'], function (translations) {
  const BUILTIN_UI_CATALOGS = {
    fr: {
      'Data Navigator': 'Navigateur de données',
      'Navigator': 'Navigateur',
      'Connectors': 'Connecteurs',
      'Connectors (%s)': 'Connecteurs (%s)',
      'Enabled Database Connectors (%s)': 'Connecteurs de bases de données activés (%s)',
      'Click any enabled engine below or expand Connectors in the Left Side Drawer to inspect local endpoints and register servers.': 'Cliquez sur un moteur activé ci-dessous ou développez Connecteurs dans le panneau gauche pour inspecter les points locaux et enregistrer des serveurs.',
      'Database Engines (On / Off)': 'Moteurs de base de données (Marche / Arrêt)',
      'Database Engines (On / Off)…': 'Moteurs de base de données (Marche / Arrêt)…',
      'Configure Database Engines…': 'Configurer les moteurs de base de données…',
      'Open Catalog Tree Drawer': 'Ouvrir le panneau du catalogue',
      'Local listener detected': 'Écoute locale détectée',
      'Enabled': 'Activé',
      'Register…': 'Enregistrer…',
      'Register Server…': 'Enregistrer un serveur…',
      'Register Server': 'Enregistrer un serveur',
      'Register Existing Database': 'Enregistrer une base existante',
      'Register Database…': 'Enregistrer une base…',
      'Create Database…': 'Créer une base de données…',
      'Create Database': 'Créer une base de données',
      'Verify / Connect…': 'Vérifier / Connecter…',
      'Re-verify / Connect…': 'Revérifier / Connecter…',
      'Verify Endpoint': 'Vérifier le point de terminaison',
      'Open in Separate Tab…': 'Ouvrir dans un onglet séparé…',
      'Remove Server…': 'Supprimer le serveur…',
      'Remove Database…': 'Retirer la base de données…',
      'Drop Database…': 'Supprimer définitivement la base…',
      'Remove…': 'Supprimer…',
      'Properties': 'Propriétés',
      'Properties…': 'Propriétés…',
      'Server Properties…': 'Propriétés du serveur…',
      'Statistics': 'Statistiques',
      'Dependencies': 'Dépendances',
      'Dependents': 'Dépendants',
      'Connection': 'Connexion',
      'Authentication': 'Authentification',
      'Advanced': 'Avancé',
      'Tags': 'Étiquettes',
      'Apply Changes': 'Appliquer les modifications',
      'Save Settings': 'Enregistrer les paramètres',
      'ScratchRobin Preferences & Workspace Settings': 'Préférences et paramètres ScratchRobin',
      'Search preferences': 'Rechercher dans les préférences',
      'Selected Object': 'Objet sélectionné',
      'Catalog': 'Catalogue',
      'Refresh Catalog': 'Actualiser le catalogue',
      'Filter Objects': 'Filtrer les objets',
      'Browse data': 'Parcourir les données',
      'Not yet verified': 'Non encore vérifié',
      'Verified / Ready': 'Vérifié / Prêt',
      'Connected / Active': 'Connecté / Actif',
      'Registered': 'Enregistré',
      'User or principal': 'Utilisateur ou principal',
      'Save Password': 'Enregistrer le mot de passe',
      'Hide password': 'Masquer le mot de passe',
      'Show password': 'Afficher le mot de passe',
      'Cancel': 'Annuler',
      'Close': 'Fermer',
      'Apply': 'Appliquer',
      'Help': 'Aide',
      'Settings': 'Paramètres',
      'Engines': 'Moteurs',
      'New': 'Nouveau',
      'Save': 'Enregistrer',
      'Undo': 'Annuler',
      'Redo': 'Rétablir',
      'Yes': 'Oui',
      'No': 'Non',
      'Delete': 'Supprimer',
    },
    de: {
      'Data Navigator': 'Daten-Navigator',
      'Navigator': 'Navigator',
      'Connectors': 'Konnektoren',
      'Connectors (%s)': 'Konnektoren (%s)',
      'Enabled Database Connectors (%s)': 'Aktivierte Datenbank-Konnektoren (%s)',
      'Database Engines (On / Off)': 'Datenbank-Engines (Ein / Aus)',
      'Database Engines (On / Off)…': 'Datenbank-Engines (Ein / Aus)…',
      'Configure Database Engines…': 'Datenbank-Engines konfigurieren…',
      'Local listener detected': 'Lokaler Dienst erkannt',
      'Enabled': 'Aktiviert',
      'Register…': 'Registrieren…',
      'Register Server…': 'Server registrieren…',
      'Register Server': 'Server registrieren',
      'Register Existing Database': 'Vorhandene Datenbank registrieren',
      'Register Database…': 'Datenbank registrieren…',
      'Create Database…': 'Datenbank erstellen…',
      'Create Database': 'Datenbank erstellen',
      'Verify / Connect…': 'Prüfen / Verbinden…',
      'Re-verify / Connect…': 'Erneut prüfen / Verbinden…',
      'Verify Endpoint': 'Endpunkt überprüfen',
      'Open in Separate Tab…': 'In separatem Tab öffnen…',
      'Remove Server…': 'Server entfernen…',
      'Remove Database…': 'Datenbank entfernen…',
      'Drop Database…': 'Datenbank löschen…',
      'Remove…': 'Entfernen…',
      'Properties': 'Eigenschaften',
      'Properties…': 'Eigenschaften…',
      'Server Properties…': 'Server-Eigenschaften…',
      'Statistics': 'Statistiken',
      'Dependencies': 'Abhängigkeiten',
      'Dependents': 'Abhängige Objekte',
      'Connection': 'Verbindung',
      'Authentication': 'Authentifizierung',
      'Advanced': 'Erweitert',
      'Tags': 'Schlagwörter',
      'Apply Changes': 'Änderungen anwenden',
      'Save Settings': 'Einstellungen speichern',
      'ScratchRobin Preferences & Workspace Settings': 'ScratchRobin-Einstellungen & Arbeitsbereich',
      'Search preferences': 'Einstellungen durchsuchen',
      'Selected Object': 'Ausgewähltes Objekt',
      'Catalog': 'Katalog',
      'Refresh Catalog': 'Katalog aktualisieren',
      'Filter Objects': 'Objekte filtern',
      'Browse data': 'Daten durchsuchen',
      'Not yet verified': 'Noch nicht überprüft',
      'Verified / Ready': 'Überprüft / Bereit',
      'Connected / Active': 'Verbunden / Aktiv',
      'Registered': 'Registriert',
      'User or principal': 'Benutzer oder Prinzipal',
      'Save Password': 'Passwort speichern',
      'Hide password': 'Passwort ausblenden',
      'Show password': 'Passwort anzeigen',
      'Cancel': 'Abbrechen',
      'Close': 'Schließen',
      'Apply': 'Anwenden',
      'Help': 'Hilfe',
      'Settings': 'Einstellungen',
      'Engines': 'Engines',
      'New': 'Neu',
      'Save': 'Speichern',
      'Undo': 'Rückgängig',
      'Redo': 'Wiederholen',
      'Yes': 'Ja',
      'No': 'Nein',
      'Delete': 'Löschen',
    },
    es: {
      'Data Navigator': 'Navegador de datos',
      'Navigator': 'Navegador',
      'Connectors': 'Conectores',
      'Connectors (%s)': 'Conectores (%s)',
      'Enabled Database Connectors (%s)': 'Conectores de bases de datos habilitados (%s)',
      'Database Engines (On / Off)': 'Motores de base de datos (Activar / Desactivar)',
      'Database Engines (On / Off)…': 'Motores de base de datos (Activar / Desactivar)…',
      'Local listener detected': 'Servicio local detectado',
      'Register…': 'Registrar…',
      'Register Server…': 'Registrar servidor…',
      'Verify / Connect…': 'Verificar / Conectar…',
      'Verify Endpoint': 'Verificar punto de conexión',
      'Create Database…': 'Crear base de datos…',
      'Register Database…': 'Registrar base de datos…',
      'Open in Separate Tab…': 'Abrir en pestaña separada…',
      'Remove Server…': 'Quitar servidor…',
      'Properties': 'Propiedades',
      'Statistics': 'Estadísticas',
      'Apply Changes': 'Aplicar cambios',
      'Save Settings': 'Guardar configuración',
      'User or principal': 'Usuario o principal',
      'Save Password': 'Guardar contraseña',
      'Hide password': 'Ocultar contraseña',
      'Show password': 'Mostrar contraseña',
      'Cancel': 'Cancelar',
      'Close': 'Cerrar',
      'Apply': 'Aplicar',
      'Help': 'Ayuda',
      'Settings': 'Configuración',
    },
    ja: {
      'Data Navigator': 'データナビゲーター',
      'Navigator': 'ナビゲーター',
      'Connectors': 'コネクター',
      'Connectors (%s)': 'コネクター (%s)',
      'Enabled Database Connectors (%s)': '有効なデータベースコネクター (%s)',
      'Database Engines (On / Off)…': 'データベースエンジン (オン / オフ)…',
      'Local listener detected': 'ローカルリスナー検出済み',
      'Register…': '登録…',
      'Register Server…': 'サーバーを登録…',
      'Verify / Connect…': '検証 / 接続…',
      'Verify Endpoint': 'エンドポイントの検証',
      'Create Database…': 'データベースを作成…',
      'Register Database…': 'データベースを登録…',
      'Open in Separate Tab…': '別のタブで開く…',
      'Remove Server…': 'サーバーを削除…',
      'Properties': 'プロパティ',
      'Statistics': '統計情報',
      'Apply Changes': '変更を適用',
      'Save Settings': '設定を保存',
      'User or principal': 'ユーザーまたはプリンシパル',
      'Save Password': 'パスワードを保存',
      'Hide password': 'パスワードを隠す',
      'Show password': 'パスワードを表示',
      'Cancel': 'キャンセル',
      'Close': '閉じる',
      'Apply': '適用',
      'Help': 'ヘルプ',
      'Settings': '設定',
    },
  };

  let currentLocale = 'en';
  let catalogRevision = 0;
  const reverseLookup = new Map();

  // Seed reverse lookup from any initial server-rendered translations.
  if (translations && typeof translations === 'object') {
    Object.keys(translations).forEach((msgid) => {
      const val = translations[msgid];
      if (typeof val === 'string' && val && val !== msgid) {
        reverseLookup.set(val, msgid);
      }
    });
  }

  function lookupRawTranslation(text) {
    if (typeof text !== 'string' || !text) return text;
    if (translations[text]) return translations[text];
    if (text.includes('…')) {
      const asciiKey = text.replace(/…/g, '...');
      if (translations[asciiKey]) return translations[asciiKey];
    } else if (text.includes('...')) {
      const ellipsisKey = text.replace(/\.\.\./g, '…');
      if (translations[ellipsisKey]) return translations[ellipsisKey];
    }
    return text;
  }

  function gettext(text) {
    let rawTranslation = lookupRawTranslation(text);
    if (typeof text === 'string' && typeof rawTranslation === 'string' && rawTranslation !== text) {
      reverseLookup.set(rawTranslation, text);
    }

    if (arguments.length <= 1) {
      return rawTranslation;
    }

    try {
      let replaceArgs = arguments;
      return rawTranslation.split('%s')
        .map(function(w, i) {
          if (i > 0) {
            if (i < replaceArgs.length) {
              return [replaceArgs[i], w].join('');
            } else {
              return ['%s', w].join('');
            }
          } else {
            return w;
          }
        })
        .join('');
    } catch (e) {
      console.error(e);
      return rawTranslation;
    }
  }

  gettext.setCatalog = function(nextCatalog, localeCode) {
    const normalizedLocale = String(localeCode || 'en').trim() || 'en';
    const baseLang = normalizedLocale.split(/[-_]/)[0];
    Object.keys(translations).forEach((k) => {
      delete translations[k];
    });
    if (normalizedLocale !== 'en') {
      const builtin = BUILTIN_UI_CATALOGS[normalizedLocale] || BUILTIN_UI_CATALOGS[baseLang] || null;
      if (builtin) {
        Object.keys(builtin).forEach((msgid) => {
          const val = builtin[msgid];
          translations[msgid] = val;
          reverseLookup.set(val, msgid);
        });
      }
      if (nextCatalog && typeof nextCatalog === 'object') {
        Object.keys(nextCatalog).forEach((msgid) => {
          const val = nextCatalog[msgid];
          if (typeof val === 'string' && val) {
            translations[msgid] = val;
            if (val !== msgid) {
              reverseLookup.set(val, msgid);
            }
          }
        });
      }
    }
    const changed = currentLocale !== normalizedLocale || Boolean(nextCatalog);
    currentLocale = normalizedLocale;
    catalogRevision += 1;
    if (typeof document !== 'undefined' && document.documentElement) {
      document.documentElement.lang = normalizedLocale;
    }
    if (changed && typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
      window.dispatchEvent(
        new CustomEvent('scratchrobin:language-changed', {
          detail: {locale: currentLocale, revision: catalogRevision},
        })
      );
    }
    return catalogRevision;
  };

  gettext.getLocale = function() {
    return currentLocale;
  };

  gettext.getRevision = function() {
    return catalogRevision;
  };

  gettext.retranslate = function(value) {
    if (typeof value !== 'string' || !value) return value;
    const msgid = reverseLookup.get(value) || value;
    return gettext(msgid);
  };

  return gettext;
});
