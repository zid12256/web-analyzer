# Web Analyzer

Outil d'analyse de sites web : **performance, SEO, accessibilité, sécurité, liens**.
Disponible en **interface web (UI)** et en **ligne de commande (CLI)**.

---

## Installation

```bash
pip install -r requirements.txt
```

Optionnel — clé API Google PageSpeed (pour plus de quota) :

```bash
export PAGESPEED_API_KEY="votre_clé"
```

---

## Interface web (recommandé)

```bash
python3 app.py
```

Puis ouvrez **http://127.0.0.1:5000** dans votre navigateur.

### Fonctionnalités de l'UI

- **Page d'accueil** : entrez une URL, choisissez les modules, lancez l'analyse en un clic
- **Barre de progression en direct** pendant l'analyse
- **Page de résultats** :
  - Jauge globale animée + barres par module
  - Graphique radar des 4 dimensions
  - Compteurs critique / avertissement / OK
  - Core Web Vitals (FCP, LCP, TBT, CLS, etc.)
  - Bar chart des opportunités de performance
  - Liste détaillée de tous les problèmes par section
  - Graphique d'évolution dans le temps (si analyses précédentes)
- **Historique** : toutes les analyses passées, filtrables, supprimables
- **Comparaison multi-sites** : sélectionnez 2+ analyses → radar + barres comparatives
- **Exports** : PDF, Excel (.xlsx), CSV, JSON

---

## CLI (ligne de commande)

```bash
# Analyse complète
python3 analyze.py https://exemple.com

# Modules spécifiques
python3 analyze.py exemple.com --only performance seo

# Sortie JSON
python3 analyze.py exemple.com --json

# Export PDF
python3 analyze.py exemple.com --pdf
```

Toutes les analyses CLI sont aussi enregistrées dans l'historique, donc visibles dans l'UI.

---

## Structure

```
web-analyzer/
├── app.py              # Serveur Flask (UI)
├── analyze.py          # CLI
├── database.py         # SQLite historique
├── exporters.py        # Excel / CSV
├── reporter.py         # Affichage terminal
├── pdf_reporter.py     # Export PDF
├── modules/            # Analyseurs (perf, seo, a11y, security, links)
├── templates/          # HTML Jinja2
├── exports/            # Fichiers exportés
└── history.db          # Base SQLite (créée auto)
```

---

## Modules d'analyse

- **Performance** — Google PageSpeed / Lighthouse, TTFB, Core Web Vitals, opportunités
- **SEO** — title, meta, h1, Open Graph, robots.txt, sitemap, JSON-LD
- **Accessibilité** — alt text, ARIA, contraste, structure des headings, lang
- **Sécurité** — HTTPS, en-têtes de sécurité (HSTS, CSP...), SSL, TLS, cookies
- **Liens** — détection des liens cassés, redirections, mixed content
