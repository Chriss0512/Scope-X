# Änderungen

## 2.0.0

**Rollen und Zugänge**

- Rollenmodell mit Gast, Mitarbeiter und Administrator. Jede schreibende
  Route prüft die Rolle serverseitig; das bestehende Konto wird bei der
  Migration Administrator.
- Registrierung nur noch mit gültiger Einladung. Codes werden ausschließlich
  als Hash gespeichert und einmal im Klartext angezeigt.
- Administrationsbereich: Konten einsehen, Rollen ändern, Konten sperren,
  Zurücksetzungs-Links erzeugen, Einladungen verwalten.
- Eingriffe in fremde Konten verlangen einen frischen Code aus der
  Authenticator-App. Ein Vertrauensgerät hilft dabei ausdrücklich nicht.
- Der letzte aktive Administrator kann sich nicht selbst entmachten.

**Anmeldung**

- Passwort-Hashing auf Argon2id umgestellt. Bestehende scrypt-Hashes werden
  bei der nächsten Anmeldung still gehoben, niemand muss sein Passwort
  ändern.
- Passwort vergessen über einen Link per Mail. Der Link allein genügt nicht:
  zusätzlich ist der zweite Faktor nötig.
- Vertrauensgerät: auf Wunsch entfällt der TOTP-Code bei der Anmeldung für
  90 Tage. Im Profil einsehbar und jederzeit widerrufbar.
- Automatische Abmeldung bei Leerlauf, serverseitig durchgesetzt, vom
  Administrator einstellbar.

**Betrieb**

- SMTP-Zugangsdaten als Add-on-Optionen, Passwortfeld maskiert.
- Ohne Mailversand bleibt alles nutzbar: Einladungen und
  Zurücksetzungs-Links lassen sich anzeigen und von Hand weitergeben.

## 1.1.0

- Anmeldung wahlweise über Benutzername oder E-Mail-Adresse, unabhängig von
  Groß- und Kleinschreibung. Beide Angaben stehen sichtbar im Profil.
- Datentabellen laufen auf schmalen Displays nicht mehr über den Kartenrand.

## 1.0.0

- Erste Fassung: Erfassung, Dashboard, PDF-Nachweis, Sicherung und
  Wiederherstellung, Zwei-Faktor-Authentifizierung, Bearbeitungssperre mit
  Änderungsprotokoll.
