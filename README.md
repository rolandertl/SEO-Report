# SEO-Report – Internes Agentur-Tool

Dieses Tool dient der automatisierten Erstellung von SEO-Reports für unsere Kunden.
Es kombiniert mehrere Datenquellen (z. B. SISTRIX, Uberall) mit KI-generierten Erklärtexten
und erzeugt visuell hochwertige PDF-Reports im Agenturdesign.

---

## Ziel

- Einfache Report-Erstellung über Domain + Zeitraum
- 10+ KPI-Blöcke
- Mehrere APIs integriert
- Einheitliches Branding
- Automatisierter PDF-Export
- Langfristig wartbare Architektur

---

# Architektur

Das System ist in 4 Ebenen unterteilt:

UI → Orchestrierung → Business-Logik → API-Layer

---

## 1. app.py (UI-Schicht)

Enthält ausschließlich:

- Streamlit UI
- Eingabe (Domain, Zeitraum)
- Trigger für Report-Generierung
- Anzeige der KPI-Blöcke
- PDF-Export

KEINE Business-Logik.
KEINE API-Details.

---

## 2. core/

### report_builder.py
Zentrale Orchestrierung.
Baut den gesamten Report aus einzelnen KPI-Blöcken zusammen.

Beispiel:
- build_visibility_block()
- build_rankings_block()
- build_backlinks_block()
- build_local_block()

### context.py
Enthält das ReportContext-Objekt.
Dieses speichert:

- Domain
- Zeitraum
- Land
- Device
- ggf. weitere Konfiguration

### config.py
Globale Einstellungen:
- Standard-Markt (AT)
- Device (Mobile)
- Farben
- Modellwahl
- API-Konfiguration

---

## 3. services/

Reine API-Wrapper.
Keine UI-Logik.

- sistrix.py
- uberall.py
- llm.py

Jede Datei:
- kümmert sich nur um Datenbeschaffung
- kennt keine Charts
- kennt kein HTML
- kennt kein Streamlit

---

## 4. metrics/

Hier steckt unsere SEO-Intelligenz.

Jedes Modul:
- ruft Daten über services ab
- berechnet Trends
- erstellt KPI-Werte
- erzeugt KI-Text
- gibt ein Block-Objekt zurück

Beispiel Rückgabe:

{
  "id": "visibility",
  "title": "Sichtbarkeit",
  "chart_html": "...",
  "comment": "...",
  "kpis": {...}
}

---

## 5. components/

Design-Schicht.

- charts.py → alle Diagramme
- cards.py → KPI-Boxen
- layout.py → visuelle Blöcke

Wenn sich das CI ändert → nur hier anpassen.

---

## 6. templates/

HTML-Struktur des Reports.

- report.html → Haupttemplate
- partials/header.html → Logo + Titel
- partials/footer.html → Footer + Seitenzahl

Styling erfolgt ausschließlich über:
assets/style.css

Python enthält KEIN Layout-Styling.

---

## 7. assets/

- logo.svg
- style.css

Hier wird das Agentur-Branding zentral verwaltet.

---

# KPI-Strategie

Geplant sind u. a.:

1. Sichtbarkeitsindex (Verlauf)
2. Ranking-Verteilung
3. Top-10 / Top-100 Entwicklung
4. Gewinner-Keywords
5. Neue Keywords
6. Wettbewerber-Vergleich
7. Backlink-Entwicklung
8. Link-Qualität
9. Local Visibility (Uberall)
10. SERP-Feature-Präsenz

Jeder KPI-Block ist modular aufgebaut.

---

# Prinzipien

- Keine Logik in app.py
- Keine Charts in services/
- Keine API-Calls in components/
- Keine HTML-Logik in metrics/
- Klare Trennung von Daten, Logik und Design

---

# Skalierbarkeit

Das System ist so aufgebaut, dass:

- neue KPIs als Modul ergänzt werden können
- neue APIs integriert werden können
- Design unabhängig von Logik geändert werden kann
- später ein White-Label möglich wäre

---

# Status

Aktuelle Version: MVP

Nächster Schritt:
- KPI-Blöcke modularisieren
- Chart-Design finalisieren
- PDF-Template verfeinern
- Uberall-Integration vorbereiten
