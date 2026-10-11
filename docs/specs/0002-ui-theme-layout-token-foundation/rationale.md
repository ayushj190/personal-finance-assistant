# 0002. UI Theme and Layout Token Foundation · Rationale

## Context

The personal finance application relies on Streamlit to render multiple complex views including financial dashboards, asset breakdowns, transaction registers, and modal dialogs. Currently, styling is fragmented across several large stylesheets (`common.css`, `custom.css`, `styles.css`) and a legacy token file (`tokens.py`).

Without a formal token foundation, interface components suffer from subtle inconsistencies:
1. Spacing, paddings, and card radii vary arbitrarily across pages.
2. Color hex codes are duplicated in both CSS rules and inline Python chart scripts.
3. Font sizes and tabular number alignments lack a unified hierarchy between narrative text and monetary figures.
4. Dark and light modes duplicate massive CSS selector blocks instead of toggling semantic CSS variables.

Establishing a clear token contract eliminates guesswork, simplifies new page development, and provides a dependable visual hierarchy tailored for financial data.

## Options considered

### Option 1: Hybrid CSS Custom Properties and Python Constants (Recommended)

CSS custom properties declared in stylesheets control all browser presentation, while Python dataclasses/constants in `ui/theme/tokens.py` mirror these values for Plotly figures and backend visual helpers.

**Pros**:
- Native CSS variables allow instant theme switching without re-executing Streamlit scripts.
- Python constants ensure Plotly charts stay pixel perfect and harmonious with CSS containers.
- Clean separation between presentation stylesheets and backend calculation logic.

**Cons**:
- Requires maintaining token parity between CSS definitions and Python constants.

### Option 2: Pure CSS Driven Architecture

All styling and variables live exclusively in CSS stylesheets. Python code injects stylesheets and passes no visual styling parameters.

**Pros**:
- Single location for design rules.

**Cons**:
- Plotly charts generate SVG/HTML canvas objects that cannot reliably read CSS custom properties from the outer DOM at render time, causing chart color drift.

### Option 3: Python Generated Runtime Stylesheet

Python dictionaries or dataclasses define all design tokens and compile dynamically into an injected `<style>` tag on every script run.

**Pros**:
- Strict single source of truth written entirely in Python.

**Cons**:
- Increases Streamlit rerun overhead by formatting and parsing large CSS strings on each interaction cycle.
- Loses browser caching and syntax highlighting advantages of static CSS files.

## Rationale

Adopting a hybrid token strategy solves the fundamental friction between browser CSS capabilities and server side Plotly Python rendering in Streamlit. CSS variables provide zero-latency theme transitions in the browser, while Python constants guarantee that cash flow charts and allocation treemaps always reflect the exact same brand and semantic color palette. 

The 8px spacing scale and 12px default card border radius provide a clean modern FinTech aesthetic, matching standard design systems like Tailwind and Material while maintaining high data density.
