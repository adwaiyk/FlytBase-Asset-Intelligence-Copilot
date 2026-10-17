# 5-Minute Video Walkthrough Script
## FlytBase Asset Intelligence Copilot — Hackathon Final Presentation

**Target Duration:** 4:45 – 5:00 minutes  
**Presenter:** Aryan  
**Screen Setup:** Browser open to `http://localhost:8501` showing the dark-mode Palantir SCADA Command Center UI with 1-click evaluation chips in the sidebar.

---

### Segment 1: System Hook & Command Center UI Overview (0:00 – 0:50)

* **[0:00 - Visual]:** Full screen view of the FLYTBASE SCADA Command Center. Hover over the top 5-card telemetry HUD showing **600 Wells**, **Online/Stopped Status**, **125,198 Inspections**, and **Anchor Date: 15 Jan 2027**.
* **[0:05 - Script]:**  
  *"Hello judges. This is our Asset Intelligence Copilot—an enterprise SCADA operations center designed for deterministic telemetry analysis, strict SOP compliance, and scoped operator memory across oil and gas fields.*  
  *We are running live against the newly dropped 600-well test dataset with over 125,000 inspections across 7 production blocks.*  
  *Notice our top HUD: our deterministic engine calculated fleet status in under 2 seconds—dynamically parsing the new T500 high-capacity ESP wells with their 25-degree thermal delta requirement, without any manual code changes."*

---

### Segment 2: Deterministic Telemetry & Boundary Awareness (0:50 – 1:50)

* **[0:50 - Visual]:** Click the **"🟢 Q1 Status Card"** or run the Q1 prompt from the test suite: *"All our wells feed one reservoir. Map the reservoir pressure across the field from the pressure data."*
* **[1:05 - Script]:**  
  *"Let's test negative grounding and boundary verification. When an operator asks to map reservoir pressure across the field, traditional LLMs hallucinate a synthetic pressure map.*  
  *Our copilot checks the underlying telemetry schema in DuckDB, verifies that surface drone inspections only capture thermal readings—not downhole reservoir pressure—and clearly reports this sensor boundary, citing the applicable SOP manual."*

* **[1:30 - Visual]:** Click the **"📋 Q2 Down Wells"** or **"📈 Q3 Thermal Trend"** chip. Point to the glowing line chart with non-producing shaded red regions.
* **[1:40 - Script]:**  
  *"When asked for thermal trends, our system renders side-by-side: grounded evidence and citation badges on the left, and an interactive Plotly dark-mode canvas on the right, highlighting exact weeks when thermal delta dropped below the well-type threshold."*

---

### Segment 3: Complex SOP Compliance & MOC Lineage (1:50 – 2:50)

* **[1:50 - Visual]:** Click or paste **Q4: Flowline Bypasses**: *"Across all areas, which temporary flowline bypasses are in place right now, and is each one allowed?"*
* **[2:00 - Script]:**  
  *"Here is our deterministic rule engine handling complex SOP compliance. Under Operations SOP OPS-2, temporary flowline bypasses require an active Management of Change memo.*  
  *Watch how the copilot cross-references MOC-2026-031, MOC-036, and MOC-044. It identifies that `WELL-0248` is legally allowed because MOC-044 extended it to February 2027. But it immediately flags `WELL-0249` as expired on December 15, and `WELL-0405` as an unapproved violation that never had an MOC."*

* **[2:30 - Visual]:** Point to the rendered audit table with status pills (Allowed in green, Expired/Not Approved in red).
* **[2:40 - Script]:**  
  *"Every single statement links directly to verified source IDs and timestamped round notes."*

---

### Segment 4: Multi-User Scoped Memory & Conflict Resolution (2:50 – 4:00)

* **[2:50 - Visual]:** In the sidebar, select **Nathan Pierce (U-601)** as the active operator. Run **Q8 Turn 1**: *"WELL-0333's recalled pump was swapped out yesterday. Please count it as replaced from now on."* Point to the `FB-0001` assertion tag.
* **[3:05 - Script]:**  
  *"Now let's demonstrate Part B: Multi-User Scoped Memory. Highline Pump Company issued a recall for lots 2409 and 2410.*  
  *Nathan Pierce logs into his console and reports that WELL-0333's recalled pump was replaced. The copilot records this as shared assertion `FB-0001` and recalculates fleet state in real time."*

* **[3:25 - Visual]:** In the sidebar, switch the operator identity to **Robert Hayes (U-301)**. Ask **Q8 Turn 3**: *"Which recalled pumps are still in the ground right now?"*
* **[3:35 - Script]:**  
  *"Now, we switch operator identities to Robert Hayes in the sidebar. When Robert asks which recalled pumps are still in the ground, notice what happens: `WELL-0333` is excluded because Nathan's operational fact was shared across all operators. But Nathan's personal conversation history and formatting preferences remain completely private and isolated to Nathan."*

* **[3:55 - Visual]:** Show the conflict handling: When an operator asserts a status that contradicts sensor telemetry, show the **`UNCONFIRMED`** badge and the conflict warning banner.

---

### Segment 5: Geospatial Spill Intelligence & Closing (4:00 – 4:55)

* **[4:00 - Visual]:** Click **"🛰️ Q7 Spill Geo-Map"** to render the PyDeck 3D Dark-Matter map with glowing ambient halo and crimson spill cores. Hover over spill markers to reveal tooltips.
* **[4:15 - Script]:**  
  *"For incident command, our geospatial canvas utilizes PyDeck on a Dark-Matter Carto style with dual-layer glow scatterplots. Hovering over any pad reveals spill volume, discovery date, and SOP containment deadlines.*  
  *All calculations—from downtime quantification to freeze protection and soil sampling compliance—are computed deterministically in DuckDB and SQLite, while Gemma 4 handles plain-English reasoning without hallucinating data."*

* **[4:40 - Visual]:** Zoom out to show the complete Command Center layout with HUD, Bento columns, and live telemetry.
* **[4:45 - Script]:**  
  *"By combining strict multi-user privacy, shared assertion propagation, and deterministic telemetry execution, the FlytBase Asset Intelligence Copilot delivers audit-grade operations intelligence for critical field infrastructure. Thank you!"*
