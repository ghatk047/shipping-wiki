#!/usr/bin/env bash
# setup_shipping_wiki_folders.sh - create the local folder tree for the Shipping Process Wiki
# Run once:  bash scripts/setup_shipping_wiki_folders.sh
set -euo pipefail

ROOT="${1:-$HOME/Projects/shipping-wiki}"
echo "Creating Shipping Process Wiki tree under: $ROOT"
mkdir -p "$ROOT"
cd "$ROOT"

# local-only working folders (never pushed)
mkdir -p data diagrams scripts

# published assets
mkdir -p assets/css assets/js assets/img

# enterprise architecture
mkdir -p ea-diagrams
for d in ea-01 ea-02 ea-03 ea-04 ea-05 ea-06 ea-07 ea-08 ea-09 ea-10; do mkdir -p "ea-diagrams/$d"; done

# 16 L1 domains / 37 L2 groups / 300 process folders

# VO - Vessel Operations & Navigation
mkdir -p vessel-operations
mkdir -p vessel-operations/voyage-planning
for p in vo-np-01 vo-np-02 vo-np-03 vo-np-04 vo-np-05 vo-np-06 vo-np-07 vo-np-08; do mkdir -p "vessel-operations/voyage-planning/$p"; done
mkdir -p vessel-operations/deck-bridge-operations
for p in vo-dc-01 vo-dc-02 vo-dc-03 vo-dc-04 vo-dc-05 vo-dc-06 vo-dc-07 vo-dc-08 vo-dc-09 vo-dc-10; do mkdir -p "vessel-operations/deck-bridge-operations/$p"; done
mkdir -p vessel-operations/engine-room
for p in vo-en-01 vo-en-02 vo-en-03 vo-en-04 vo-en-05 vo-en-06 vo-en-07 vo-en-08 vo-en-09 vo-en-10; do mkdir -p "vessel-operations/engine-room/$p"; done

# CM - Container & Terminal Management
mkdir -p container-terminal
mkdir -p container-terminal/terminal-operating-system
for p in cm-tos-01 cm-tos-02 cm-tos-03 cm-tos-04 cm-tos-05 cm-tos-06 cm-tos-07 cm-tos-08; do mkdir -p "container-terminal/terminal-operating-system/$p"; done
mkdir -p container-terminal/cargo-planning
for p in cm-cp-01 cm-cp-02 cm-cp-03 cm-cp-04 cm-cp-05 cm-cp-06 cm-cp-07 cm-cp-08; do mkdir -p "container-terminal/cargo-planning/$p"; done
mkdir -p container-terminal/container-equipment
for p in cm-eq-01 cm-eq-02 cm-eq-03 cm-eq-04 cm-eq-05 cm-eq-06 cm-eq-07 cm-eq-08; do mkdir -p "container-terminal/container-equipment/$p"; done

# FF - Freight Forwarding & Booking
mkdir -p freight-forwarding
mkdir -p freight-forwarding/freight-booking
for p in ff-bk-01 ff-bk-02 ff-bk-03 ff-bk-04 ff-bk-05 ff-bk-06 ff-bk-07 ff-bk-08; do mkdir -p "freight-forwarding/freight-booking/$p"; done
mkdir -p freight-forwarding/shipping-documentation
for p in ff-doc-01 ff-doc-02 ff-doc-03 ff-doc-04 ff-doc-05 ff-doc-06 ff-doc-07 ff-doc-08; do mkdir -p "freight-forwarding/shipping-documentation/$p"; done
mkdir -p freight-forwarding/freight-tracking
for p in ff-tr-01 ff-tr-02 ff-tr-03 ff-tr-04 ff-tr-05 ff-tr-06 ff-tr-07 ff-tr-08; do mkdir -p "freight-forwarding/freight-tracking/$p"; done

# CD - Customs, Trade & Documentation
mkdir -p customs-trade
mkdir -p customs-trade/export-customs
for p in cd-ex-01 cd-ex-02 cd-ex-03 cd-ex-04 cd-ex-05 cd-ex-06 cd-ex-07 cd-ex-08; do mkdir -p "customs-trade/export-customs/$p"; done
mkdir -p customs-trade/import-customs
for p in cd-im-01 cd-im-02 cd-im-03 cd-im-04 cd-im-05 cd-im-06 cd-im-07 cd-im-08; do mkdir -p "customs-trade/import-customs/$p"; done
mkdir -p customs-trade/trade-compliance
for p in cd-tr-01 cd-tr-02 cd-tr-03 cd-tr-04 cd-tr-05 cd-tr-06 cd-tr-07 cd-tr-08; do mkdir -p "customs-trade/trade-compliance/$p"; done

# SC - Supply Chain & Logistics
mkdir -p supply-chain
mkdir -p supply-chain/warehousing
for p in sc-wh-01 sc-wh-02 sc-wh-03 sc-wh-04 sc-wh-05 sc-wh-06 sc-wh-07 sc-wh-08; do mkdir -p "supply-chain/warehousing/$p"; done
mkdir -p supply-chain/land-transport
for p in sc-lnd-01 sc-lnd-02 sc-lnd-03 sc-lnd-04 sc-lnd-05 sc-lnd-06 sc-lnd-07 sc-lnd-08; do mkdir -p "supply-chain/land-transport/$p"; done
mkdir -p supply-chain/air-freight
for p in sc-af-01 sc-af-02 sc-af-03 sc-af-04 sc-af-05 sc-af-06 sc-af-07 sc-af-08; do mkdir -p "supply-chain/air-freight/$p"; done

# FM - Fleet Management & Maintenance
mkdir -p fleet-maintenance
mkdir -p fleet-maintenance/planned-maintenance
for p in fm-pm-01 fm-pm-02 fm-pm-03 fm-pm-04 fm-pm-05 fm-pm-06 fm-pm-07 fm-pm-08; do mkdir -p "fleet-maintenance/planned-maintenance/$p"; done
mkdir -p fleet-maintenance/port-state-control
for p in fm-ps-01 fm-ps-02 fm-ps-03 fm-ps-04 fm-ps-05 fm-ps-06 fm-ps-07 fm-ps-08; do mkdir -p "fleet-maintenance/port-state-control/$p"; done
mkdir -p fleet-maintenance/bunkering
for p in fm-bk-01 fm-bk-02 fm-bk-03 fm-bk-04 fm-bk-05 fm-bk-06 fm-bk-07 fm-bk-08; do mkdir -p "fleet-maintenance/bunkering/$p"; done

# RM - Revenue Management & Pricing
mkdir -p revenue-management
mkdir -p revenue-management/rate-management
for p in rm-rt-01 rm-rt-02 rm-rt-03 rm-rt-04 rm-rt-05 rm-rt-06 rm-rt-07 rm-rt-08; do mkdir -p "revenue-management/rate-management/$p"; done
mkdir -p revenue-management/yield-management
for p in rm-ym-01 rm-ym-02 rm-ym-03 rm-ym-04 rm-ym-05 rm-ym-06 rm-ym-07 rm-ym-08; do mkdir -p "revenue-management/yield-management/$p"; done

# CS - Customer Service & Sales
mkdir -p customer-service
mkdir -p customer-service/sales-account-management
for p in cs-sl-01 cs-sl-02 cs-sl-03 cs-sl-04 cs-sl-05 cs-sl-06 cs-sl-07 cs-sl-08; do mkdir -p "customer-service/sales-account-management/$p"; done
mkdir -p customer-service/customer-service-operations
for p in cs-sv-01 cs-sv-02 cs-sv-03 cs-sv-04 cs-sv-05 cs-sv-06 cs-sv-07 cs-sv-08; do mkdir -p "customer-service/customer-service-operations/$p"; done

# HS - HSSE & Quality Management
mkdir -p hsse-quality
mkdir -p hsse-quality/safety-emergency
for p in hs-sf-01 hs-sf-02 hs-sf-03 hs-sf-04 hs-sf-05 hs-sf-06 hs-sf-07 hs-sf-08; do mkdir -p "hsse-quality/safety-emergency/$p"; done
mkdir -p hsse-quality/environmental-quality
for p in hs-en-01 hs-en-02 hs-en-03 hs-en-04 hs-en-05 hs-en-06 hs-en-07 hs-en-08; do mkdir -p "hsse-quality/environmental-quality/$p"; done

# HR - Human Resources & Crew Management
mkdir -p hr-crew
mkdir -p hr-crew/crew-management
for p in hr-cr-01 hr-cr-02 hr-cr-03 hr-cr-04 hr-cr-05 hr-cr-06 hr-cr-07 hr-cr-08; do mkdir -p "hr-crew/crew-management/$p"; done
mkdir -p hr-crew/shore-hr
for p in hr-sh-01 hr-sh-02 hr-sh-03 hr-sh-04 hr-sh-05 hr-sh-06 hr-sh-07 hr-sh-08; do mkdir -p "hr-crew/shore-hr/$p"; done

# FN - Finance & Accounting
mkdir -p finance-accounting
mkdir -p finance-accounting/voyage-accounting
for p in fn-va-01 fn-va-02 fn-va-03 fn-va-04 fn-va-05 fn-va-06 fn-va-07 fn-va-08; do mkdir -p "finance-accounting/voyage-accounting/$p"; done
mkdir -p finance-accounting/corporate-finance
for p in fn-cf-01 fn-cf-02 fn-cf-03 fn-cf-04 fn-cf-05 fn-cf-06 fn-cf-07 fn-cf-08; do mkdir -p "finance-accounting/corporate-finance/$p"; done

# IT - IT, Digital & Cybersecurity
mkdir -p it-digital
mkdir -p it-digital/it-operations
for p in it-op-01 it-op-02 it-op-03 it-op-04 it-op-05 it-op-06 it-op-07 it-op-08; do mkdir -p "it-digital/it-operations/$p"; done
mkdir -p it-digital/cybersecurity
for p in it-cy-01 it-cy-02 it-cy-03 it-cy-04 it-cy-05 it-cy-06 it-cy-07 it-cy-08; do mkdir -p "it-digital/cybersecurity/$p"; done

# PR - Procurement & Supply Chain
mkdir -p procurement
mkdir -p procurement/strategic-procurement
for p in pr-sp-01 pr-sp-02 pr-sp-03 pr-sp-04 pr-sp-05 pr-sp-06 pr-sp-07 pr-sp-08; do mkdir -p "procurement/strategic-procurement/$p"; done
mkdir -p procurement/operational-procurement
for p in pr-op-01 pr-op-02 pr-op-03 pr-op-04 pr-op-05 pr-op-06 pr-op-07 pr-op-08; do mkdir -p "procurement/operational-procurement/$p"; done

# SU - Sustainability & Decarbonisation
mkdir -p sustainability
mkdir -p sustainability/decarbonisation
for p in su-dc-01 su-dc-02 su-dc-03 su-dc-04 su-dc-05 su-dc-06 su-dc-07 su-dc-08; do mkdir -p "sustainability/decarbonisation/$p"; done
mkdir -p sustainability/esg-reporting
for p in su-es-01 su-es-02 su-es-03 su-es-04 su-es-05 su-es-06 su-es-07 su-es-08; do mkdir -p "sustainability/esg-reporting/$p"; done

# IM - Intermodal & Last Mile Logistics
mkdir -p intermodal
mkdir -p intermodal/intermodal-operations
for p in im-in-01 im-in-02 im-in-03 im-in-04 im-in-05 im-in-06 im-in-07 im-in-08; do mkdir -p "intermodal/intermodal-operations/$p"; done

# LG - Legal, Regulatory & Insurance
mkdir -p legal-regulatory
mkdir -p legal-regulatory/legal-insurance
for p in lg-li-01 lg-li-02 lg-li-03 lg-li-04 lg-li-05 lg-li-06 lg-li-07 lg-li-08; do mkdir -p "legal-regulatory/legal-insurance/$p"; done
mkdir -p legal-regulatory/regulatory-affairs
for p in lg-rg-01 lg-rg-02 lg-rg-03 lg-rg-04 lg-rg-05 lg-rg-06 lg-rg-07 lg-rg-08; do mkdir -p "legal-regulatory/regulatory-affairs/$p"; done

# git + ignores
if [ ! -d .git ]; then
  git init -q -b main
  git remote add origin https://github.com/ghatk047/shipping-wiki.git 2>/dev/null || true
fi

cat > .gitignore <<'IGN'
.venv/
data/
diagrams/
__pycache__/
*.pyc
.DS_Store
IGN

touch .nojekyll

COUNT=$(find . -mindepth 3 -maxdepth 3 -type d -not -path "./.git/*" | wc -l | tr -d " ")
echo "Done. Process folders created: $COUNT (expected 300)"
echo
echo "Next:"
echo "  1. cp wiki.css assets/css/ ; cp wiki.js assets/js/"
echo "  2. cp generate_shipping_wiki.py generate_shipping_ea.py scripts/"
echo "  3. python3 -m venv .venv ; source .venv/bin/activate ; pip install requests openpyxl"
echo "  4. export GITHUB_TOKEN=your_new_token"
echo "  5. python3 scripts/generate_shipping_wiki.py --bootstrap"
echo "  6. Enable Pages: Settings > Pages > Deploy from branch > main > / (root)"
echo "  7. python3 scripts/generate_shipping_wiki.py   # pilot VO-NP-01 + CM-TOS-01"
