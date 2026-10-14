---
name: dwp-ui-design-system
description: Standard UI/UX design system and layout guidelines for DWP Field Assistant Engine. Enforces sleek Corporate Claymorphism design with balanced 3D inflated surfaces, tactile inner/outer shadows, rounded clay cards (16px-20px), clay pill badges, and seamless Light/Dark mode adaptability.
---

# DWP Field Assistant UI/UX Design System: Sleek Corporate Claymorphism

This skill defines the authoritative design system, typography guidelines, and layout principles for all UI modules in the **DWP Field Assistant Engine** (`estimator`). Any agent modifying or extending the interface MUST strictly follow these rules.

---

## 🎨 1. Corporate Claymorphism Aesthetic & Color Palette

Claymorphism transforms traditional flat interfaces into tactile, friendly, physical-feeling 3D clay surfaces while maintaining high contrast, corporate sophistication, and strict readability.

### Core Visual Attributes:
1. **Inflated 3D Matte Surfaces**: Non-glossy, soft-feel surfaces created through double-layer lighting (outer elevation drop-shadow + subtle inner inset bevels).
2. **Generous Rounded Corners**: 
   - Cards and Step Containers: `border-radius: 16px - 20px;`
   - Badges and Action Pills: `border-radius: 9999px;` or `14px;`
   - Inputs and Selectboxes: `border-radius: 12px;`
3. **Tactile Micro-Interactions**:
   - Hover state: Gentle lift (`transform: translateY(-2px);`) with expanded soft shadow.
   - Active / Click state: Physical clay compression (`transform: translateY(1px);`) with reduced shadow.

---

## 🌓 2. Adaptive Light & Dark Mode Clay Tokens

All custom CSS variables adapt automatically using Streamlit's base theme variables:

### Light Mode:
- **Surface Fill**: Soft porcelain / cloud (`#F4F7FC` / `rgba(240, 244, 250, 0.85)`)
- **Text Color**: Deep charcoal / obsidian (`#0F172A` via `var(--text-color)`)
- **Outer Drop Shadow**: `8px 8px 18px rgba(166, 178, 200, 0.35), -6px -6px 14px rgba(255, 255, 255, 0.85)`
- **Inner Inset Shadow**: `inset 2px 2px 4px rgba(255, 255, 255, 0.7), inset -2px -2px 4px rgba(166, 178, 200, 0.25)`
- **Border**: `1px solid rgba(255, 255, 255, 0.6)`

### Dark Mode:
- **Surface Fill**: Deep obsidian / dark titanium (`#181C26` / `rgba(24, 28, 38, 0.9)`)
- **Text Color**: Crisp snow white (`#F8FAFC` via `var(--text-color)`)
- **Outer Drop Shadow**: `8px 8px 20px rgba(0, 0, 0, 0.6), -4px -4px 12px rgba(255, 255, 255, 0.04)`
- **Inner Inset Shadow**: `inset 2px 2px 4px rgba(255, 255, 255, 0.07), inset -2px -2px 4px rgba(0, 0, 0, 0.45)`
- **Border**: `1px solid rgba(255, 255, 255, 0.08)`

---

## ✒️ 3. Typography & Hierarchy
- **Main App Title:** `font-size: 1.6rem; font-weight: 800; letter-spacing: -0.02em;`
- **Sub-titles & Captions:** `font-size: 0.86rem; opacity: 0.8;`
- **Step Headers (`.dwp-step-title`):** `font-weight: 700; font-size: 1.0rem;`
- **Part Descriptions:** `font-weight: 700; font-size: 0.95rem;`
- **Prices & Totals:** `font-weight: 800; font-size: 1.1rem;`
- **Monospace SKUs:** `font-family: monospace; font-size: 0.84rem; font-weight: 700;`

---

## 📐 4. High-Productivity 2-Column Split Dashboard Flow

Avoid endless single-column scrolling. Tab 1 utilizes a split desktop layout:
- **Left Column (Parts Explorer)**:
  - Step 1: Model Selection.
  - Step 2: Sub-Assembly Category filter, Part search input, Branch inventory toggle.
  - Bounded scroll container (`st.container(height=560)`) displaying individual clay component cards with SKU, description, stock status pill, frequency badge, and cross-model fit.
- **Right Column (Sticky Live Quotation & Checkout)**:
  - Live Selected Parts Cart with individual remove and clear all controls.
  - Step 3: Service charges & customer warranty radio.
  - Step 4: Customer name, phone, serial inputs.
  - Real-time Official Estimate Bill Receipt.
  - Instant WhatsApp 1-click quotation launcher.

---

## 🚀 5. Quality Verification & Git Protocol
- Test interface across both **Light Mode** and **Dark Mode** to ensure shadows, contrast, and text remain crisp.
- **Mandatory Git Push**: Every change must be committed with a descriptive git message and pushed to GitHub immediately.
