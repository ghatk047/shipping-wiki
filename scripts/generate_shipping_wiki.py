#!/usr/bin/env python3
"""
generate_shipping_wiki.py — Shipping Industry Process Wiki generator
Reference company: A.P. Moller-Maersk A/S
Repo: https://github.com/ghatk047/shipping-wiki
Pages: https://ghatk047.github.io/shipping-wiki/

Flags
  (none)            pilot — VO-NP-01 and CM-TOS-01
  --full            all incomplete processes
  --count N         next N incomplete processes
  --start PID       resume from PID (in catalogue order)
  --pid PID         single process
  --no-verify       skip the 90s live-page verification
  --bootstrap       push shell only (.nojekyll, css, js, search.html, indexes) and exit
  --rebuild-nav     regenerate and push every index + search index, no Ollama calls

Token comes from the environment, never from this file:
    export GITHUB_TOKEN=ghp_xxx
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from base64 import b64encode
from datetime import datetime
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

REPO_OWNER = "ghatk047"
REPO_NAME  = "shipping-wiki"
BRANCH     = "main"
PAGES_BASE = f"https://{REPO_OWNER}.github.io/{REPO_NAME}"
GH_API     = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents"

SITE_TITLE = "Maersk Shipping Process Wiki"
SITE_SUB   = "Ocean Container Shipping &amp; Integrated Logistics"

OLLAMA_URL      = "http://localhost:11434"
PRIMARY_MODEL   = "qwen2.5-coder:14b"
FALLBACK_MODEL  = "qwen2.5:latest"
OLLAMA_TIMEOUT  = 600

ROOT        = Path(__file__).resolve().parent.parent      # ~/Projects/shipping-wiki
DATA_DIR    = ROOT / "data"
DIAGRAM_DIR = ROOT / "diagrams"
IMG_DIR     = ROOT / "assets" / "img"
TRACKER     = DATA_DIR / "processes.json"
EXCEL_PATH  = DATA_DIR / "Shipping_Process_Wiki.xlsx"

INIT_LINE = ("%%{init: {'theme':'base','themeVariables':"
             "{'fontSize':'13px','fontFamily':'Helvetica Neue, Helvetica, Arial, sans-serif'}}}%%")

PID_W, PID_H = 2400, 1400
EA_W,  EA_H  = 3840, 2160
MMDC_SCALE   = 2
VERIFY_WAIT  = 90

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()

# ─────────────────────────────────────────────────────────────────────────────
# TAXONOMY — 16 L1 domains, 38 L2 groups, 300 processes
# ─────────────────────────────────────────────────────────────────────────────

L1_META = {
    "VO": ("\U0001F6A2", "Vessel Operations & Navigation",      "vessel-operations"),
    "CM": ("\U0001F3D7",  "Container & Terminal Management",     "container-terminal"),
    "FF": ("\U0001F4E6", "Freight Forwarding & Booking",        "freight-forwarding"),
    "CD": ("\U0001F6C3", "Customs, Trade & Documentation",      "customs-trade"),
    "SC": ("\U0001F517", "Supply Chain & Logistics",            "supply-chain"),
    "FM": ("\u2699",      "Fleet Management & Maintenance",      "fleet-maintenance"),
    "RM": ("\U0001F4B2", "Revenue Management & Pricing",        "revenue-management"),
    "CS": ("\U0001F91D", "Customer Service & Sales",            "customer-service"),
    "HS": ("\U0001F9BA", "HSSE & Quality Management",           "hsse-quality"),
    "HR": ("\U0001F465", "Human Resources & Crew Management",   "hr-crew"),
    "FN": ("\U0001F4B0", "Finance & Accounting",                "finance-accounting"),
    "IT": ("\U0001F510", "IT, Digital & Cybersecurity",         "it-digital"),
    "PR": ("\U0001F6D2", "Procurement & Supply Chain",          "procurement"),
    "SU": ("\U0001F33F", "Sustainability & Decarbonisation",    "sustainability"),
    "IM": ("\U0001F69B", "Intermodal & Last Mile Logistics",    "intermodal"),
    "LG": ("\u2696",      "Legal, Regulatory & Insurance",       "legal-regulatory"),
}

# (l1, l2, l2_name, l2_slug, [process names in order])
TAXONOMY = [
("VO", "NP", "Voyage Planning & Navigation", "voyage-planning", [
    "Pre-Voyage Route Optimisation and Weather Routing",
    "Port Call Planning and Berth Scheduling",
    "Fuel Planning and Bunker Strategy with Slow Steaming Optimisation",
    "Stability Calculation and Trim Optimisation Pre-Loading",
    "ECDIS Chart Updates and Passage Plan Approval",
    "Restricted Waters and Canal Transit Management",
    "Deviation and Emergency Diversion Management",
    "Voyage Performance Reporting and Speed Optimisation",
]),
("VO", "DC", "Deck and Bridge Operations", "deck-bridge-operations", [
    "Bridge Watchkeeping and COLREGS Compliance",
    "Mooring, Unmooring and Anchor Operations",
    "Pilot Boarding and Disembarkation Management",
    "AIS Reporting and LRIT Vessel Tracking",
    "Vessel Security Alert System and ISPS Compliance",
    "Fire, Flooding and Emergency Response Drills",
    "Officer of the Watch Handover Procedures",
    "Search and Rescue Coordination",
    "Medical Emergency Management at Sea",
    "Voyage Log and Official Logbook Maintenance",
]),
("VO", "EN", "Engine Room and Technical Operations", "engine-room", [
    "Main Engine Watch and Performance Monitoring",
    "Fuel Oil Management and Bunkering Operations",
    "Ballast Water Management and BWM Convention Compliance",
    "Waste Management and MARPOL Annex I to VI Compliance",
    "Auxiliary Systems Operation for Generators, Compressors and Pumps",
    "Engine Room Emergency Procedures",
    "Lubrication Oil Analysis and Condition Monitoring",
    "Shaft Generator and Power Management Optimisation",
    "Scrubber Operation and Exhaust Gas Cleaning",
    "Green Methanol and Alternative Fuel Operation",
]),
("CM", "TOS", "Terminal Operating System Operations", "terminal-operating-system", [
    "Vessel Arrival Planning and Berth Allocation in Navis N4",
    "Yard Planning and Block Allocation",
    "Quay Crane Work Queue and Vessel Stowage Sequencing",
    "Gate-In and Gate-Out Container Processing",
    "Rail and Truck Interchange at Terminal",
    "Reefer Container Monitoring and Temperature Management",
    "Dangerous Goods Yard Segregation and Compliance",
    "Terminal KPI Reporting for Crane Moves Per Hour and Dwell Time",
]),
("CM", "CP", "Cargo Planning and Stowage", "cargo-planning", [
    "Pre-Stow Planning and Bay Plan Creation",
    "Dangerous Goods Segregation and IMDG Compliance",
    "VGM Verification and Weight Accuracy Management",
    "Out of Gauge Cargo Stowage Planning",
    "Reefer Stowage and Power Point Allocation",
    "Load and Discharge List Generation and Stevedore Instructions",
    "Vessel Stability Calculation and Trim Approval",
    "Hatch Sequence Optimisation and Port Rotation Planning",
]),
("CM", "EQ", "Container Equipment Management", "container-equipment", [
    "Container Fleet Repositioning and Empty Management",
    "Container Inspection and Damage Assessment",
    "Container Repair Authorisation and Depot Management",
    "Reefer Pre-Trip Inspection and Certification",
    "Container Leasing and Return Management",
    "Container Tracking and Visibility via Remote Container Management",
    "Off-Hire Container Condition Survey",
    "Container Disposal and End-of-Life Management",
]),
("FF", "BK", "Freight Booking and Reservation", "freight-booking", [
    "Spot Rate Quote and Online Booking on Maersk.com",
    "Contract Rate Application and Service Contract Management",
    "FCL Booking Confirmation and Vessel Slot Allocation",
    "LCL Booking, Consolidation Planning and CFS Coordination",
    "Booking Amendment and Cancellation Processing",
    "Overbooking Management and Roll-Over Procedures",
    "Special Cargo Booking for OOG, DG and Reefer",
    "Group Booking and Shipper-Owned Container Management",
]),
("FF", "DOC", "Shipping Documentation", "shipping-documentation", [
    "Bill of Lading Issuance and Amendment for Master and House B/L",
    "Sea Waybill Processing and Express Release",
    "Cargo Manifest Compilation and Customs Transmission",
    "Packing List and Certificate of Origin Verification",
    "Letter of Credit Compliance and Documentary Collection",
    "Telex Release and Original B/L Surrender",
    "Dangerous Goods Declaration and IMDG Documentation",
    "Switch Bill of Lading Processing",
]),
("FF", "TR", "Freight Tracking and Visibility", "freight-tracking", [
    "Container Milestone Tracking via Maersk Track and Trace",
    "Vessel AIS and Port Arrival ETA Updates",
    "Exception Alert Management for Delays, Transshipments and Rollovers",
    "Cargo Availability Notification",
    "Proof of Delivery and eDelivery Order Processing",
    "Detention and Demurrage Notification and Billing",
    "Customer Shipment Status Reporting and API Integration",
    "Carbon Emission Reporting per Shipment for Scope 3",
]),
("CD", "EX", "Export Customs Procedures", "export-customs", [
    "Export Classification and HS Code Assignment",
    "Export Licence Determination and Controlled Goods Screening",
    "AES and ECS Export Declaration Filing",
    "Cargo Manifest Pre-filing and Advance Cargo Information",
    "Shipper Export Declaration and EEI Filing",
    "Dangerous Goods Export Compliance and ADR and IMDG Validation",
    "Sanctions Screening and OFAC and BIS Compliance",
    "Export Certificate of Origin and GSP Form Management",
]),
("CD", "IM", "Import Customs Procedures", "import-customs", [
    "Import Entry Classification and Duty Calculation",
    "Importer Security Filing and Entry Summary",
    "Entry Bond and Continuous Bond Management",
    "Tariff Engineering and Duty Drawback Management",
    "Antidumping and Countervailing Duty Screening",
    "Customs Examination, Devanning and CET Hold Management",
    "Broker-of-Record Onboarding and Power of Attorney",
    "AEO and C-TPAT Trusted Trader Programme Maintenance",
]),
("CD", "TR", "Trade Compliance and Sanctions", "trade-compliance", [
    "Denied Party Screening and OFAC and UN Sanctions List Check",
    "End-User Certificate and Military Goods Screening",
    "Russia, Belarus and North Korea Trade Restriction Compliance",
    "Free Trade Agreement Qualification and Certificate Management",
    "INCOTERMS Allocation and Liability Transfer Documentation",
    "Letters of Indemnity Issuance and Risk Assessment",
    "Trade Compliance Audit and Internal Control Testing",
    "Regulatory Change Management and Tariff Update Monitoring",
]),
("SC", "WH", "Warehousing Operations", "warehousing", [
    "Inbound Receiving and Put-Away",
    "Inventory Cycle Count and Accuracy Management",
    "Pick, Pack and Ship Order Fulfilment",
    "Value-Added Services for Kitting, Labelling and Repackaging",
    "Returns Management and Reverse Logistics",
    "Cold Chain Warehouse Management and Temperature Monitoring",
    "Cross-Docking and Flow-Through Operations",
    "Warehouse Labour Planning and Productivity Management",
]),
("SC", "LND", "Land Transport and Inland Logistics", "land-transport", [
    "Drayage and Port Pickup Coordination",
    "Over-the-Road Trucking and Carrier Management",
    "Rail Intermodal Booking and BNSF and UP Coordination",
    "Last Mile Delivery Scheduling and Route Optimisation",
    "White Glove and Specialised Cargo Delivery Management",
    "Inland Container Depot Management",
    "Cross-Border Road Transport and Cabotage Compliance",
    "Fleet Visibility and TMS Track and Trace",
]),
("SC", "AF", "Air Freight Operations", "air-freight", [
    "Air Freight Booking and IATA AWB Issuance",
    "Air Cargo Capacity Management and Charter Operations",
    "Dangerous Goods Air Freight Compliance under IATA DGR",
    "Airline Agent and Ground Handling Agent Management",
    "Air Export Screening and TSA Known Shipper Compliance",
    "Perishable and Pharma Air Cargo Management under CEIV Pharma",
    "Air Freight Customs Clearance and ACI Filing",
    "Air Freight Track and Trace and Customer Notification",
]),
("FM", "PM", "Planned Maintenance", "planned-maintenance", [
    "Planned Maintenance System Schedule Management",
    "Dry Dock Planning and Shipyard Tender Management",
    "Hull Cleaning and Anti-Fouling Coating Management",
    "Main Engine Overhaul and Top Overhaul Management",
    "Classification Survey Planning for Annual, Intermediate and Special",
    "Spare Parts Inventory and Critical Spare Management",
    "Condition-Based Monitoring and Predictive Maintenance",
    "Technical Defect Reporting and Close-Out Management",
]),
("FM", "PS", "Port State Control and Class Compliance", "port-state-control", [
    "Port State Control Inspection Preparation and Response",
    "Class Renewal Survey Coordination with DNV and Lloyd's Register",
    "Statutory Certificate Management for Safety, Load Line, MARPOL and ISM",
    "ISM Code Audit and SMS Document Control",
    "ISPS Code Audit and Vessel Security Plan Update",
    "MLC 2006 Labour Compliance Audit",
    "Deficiency and Detention Management Post-PSC Inspection",
    "Flag State Authority Communication and Reporting",
]),
("FM", "BK", "Bunkering and Fuel Management", "bunkering", [
    "Bunker Procurement and Tender Management",
    "Bunker Stem Planning and Quantity Calculation",
    "Bunker Delivery Note Verification and MARPOL Compliance",
    "Fuel Quality Testing and Off-Spec Bunker Management",
    "VLSFO and ULSFO Transition and Compatibility Testing",
    "Green Methanol and Alternative Fuel Bunkering",
    "Fuel Consumption Monitoring and CII Data Collection",
    "Bunker Hedging and Price Risk Management",
]),
("RM", "RT", "Rate Setting and Tariff Management", "rate-management", [
    "Spot Rate Setting and Market Intelligence",
    "Long-Term Contract Rate Negotiation for Service Contracts and NAC",
    "FAK Rate Management",
    "Surcharge Administration for BAF, CAF, PSS and ECA",
    "Rate Filing and Regulatory Tariff Publication",
    "Alliance Slot Cost Allocation under Gemini Cooperation",
    "Low Sulphur Bunker Adjustment Factor Calculation",
    "Peak Season Surcharge and General Rate Increase Management",
]),
("RM", "YM", "Yield Management and Revenue Optimisation", "yield-management", [
    "Vessel Load Factor Monitoring and Overbooking Strategy",
    "Trade Lane Profitability Analysis and Corridor Review",
    "Cargo Mix Optimisation for High-Value versus Commodity",
    "Demurrage and Detention Revenue Management",
    "Ancillary Revenue for Value-Added Services and Documentation Fees",
    "Proforma Voyage Profitability and Actual versus Budget Analysis",
    "Alliance Revenue Sharing and Slot Exchange Settlement",
    "Freight Forwarder Commission and Incentive Management",
]),
("CS", "SL", "Sales and Account Management", "sales-account-management", [
    "Enterprise Customer Prospecting and RFQ Management",
    "Service Contract Negotiation and Terms Agreement",
    "Key Account Management and Customer Review Meetings",
    "New Lane Development and Cargo Development",
    "Freight Forwarder Partnership and Volume Agreement",
    "E-Commerce Customer Onboarding and Maersk.com API Integration",
    "Sales Pipeline Management and Forecasting",
    "Tender Response and Win Loss Analysis",
]),
("CS", "SV", "Customer Service Operations", "customer-service-operations", [
    "Booking Exception Handling and Rollover Communication",
    "Cargo Claim Filing and Investigation under B/L Carrier Liability",
    "Complaint Management and Service Failure Resolution",
    "Detention and Demurrage Dispute Resolution",
    "Customer Portal Onboarding and API Integration Support",
    "VIP Shipper and Key Account Escalation Management",
    "Vessel Delay Communication and Proactive Exception Alerting",
    "Net Promoter Score Survey and Customer Satisfaction Tracking",
]),
("HS", "SF", "Safety and Emergency Management", "safety-emergency", [
    "Safety Management System Maintenance and Audit under ISM Code",
    "Incident Investigation and Root Cause Analysis",
    "Near-Miss and Hazard Reporting",
    "Emergency Drills for Fire, Flooding, Man Overboard and Abandon Ship",
    "Permit to Work System Management for Hot Work and Confined Space",
    "Port Reception Facility Coordination and Waste Discharge",
    "Seafarer Personal Protective Equipment and Safety Induction",
    "HSSE KPI Reporting and Board Safety Review",
]),
("HS", "EN", "Environmental and Quality Compliance", "environmental-quality", [
    "MARPOL Compliance for Oil Record Book and Garbage Record Book",
    "Ballast Water Reporting and IMO BWM Convention Compliance",
    "Noise and Vibration Monitoring for Crew Health and Marine Mammals",
    "Anti-Fouling System Compliance under AFS Convention",
    "ISO 9001 Quality Management System Audit",
    "Customer Cargo Quality Claim Investigation",
    "Reefer Cargo Temperature Excursion Investigation",
    "Bulk and Chemical Cargo Safety Protocol Management",
]),
("HR", "CR", "Seafarer and Crew Management", "crew-management", [
    "Seafarer Recruitment and STCW Certification Verification",
    "Crew Rotation Planning and Sign-On and Sign-Off Management",
    "Seafarer Payroll and Collective Bargaining Agreement Compliance",
    "STCW Refresher Training and Revalidation Management",
    "Manning Agency Management and Flag State Endorsement",
    "Seafarer Medical Fitness Certificate Management",
    "Crew Welfare and MLC 2006 Compliance Audit",
    "Crew Repatriation and Emergency Evacuation Management",
]),
("HR", "SH", "Shore Staff and Corporate HR", "shore-hr", [
    "Talent Acquisition and Global Mobility Management",
    "Performance Management and Annual Appraisal Cycle",
    "Learning and Development for the Maritime Competency Framework",
    "Compensation, Benefits and Bonus Administration",
    "Labour Relations and Works Council Engagement",
    "Diversity, Equity and Inclusion Programme Management",
    "Expatriate Assignment and Secondment Management",
    "Succession Planning and Leadership Pipeline Development",
]),
("FN", "VA", "Voyage Accounting", "voyage-accounting", [
    "Proforma Voyage Estimate and Budget",
    "Port Disbursement Account Review and Approval",
    "Freight Revenue Recognition under ASC 606 and IFRS 15",
    "Bunker Cost Allocation and Fuel Accounting",
    "Voyage Actual versus Proforma Variance Analysis",
    "Charter Party Hire Payment and Off-Hire Deduction",
    "Canal and Port Dues Invoice Verification",
    "Intercompany Vessel Cost Allocation",
]),
("FN", "CF", "Corporate Finance and Control", "corporate-finance", [
    "Month-End Close and Segment Reporting",
    "Accounts Payable Vendor Invoice and Three-Way Match",
    "Accounts Receivable and Freight Invoice Collection",
    "Treasury Cash Pooling, FX Hedging and Bunker Hedging",
    "Customs Duty Drawback and Tax Refund Management",
    "External Financial Reporting under IFRS and Danish GAAP",
    "Internal Audit for Revenue Integrity and Freight Rate Compliance",
    "SOX and GDPR Financial Controls and Documentation",
]),
("IT", "OP", "IT Operations and Infrastructure", "it-operations", [
    "SAP S/4HANA System Administration and Release Management",
    "Navis N4 TOS Administration and Terminal Interface Management",
    "Azure Cloud Infrastructure Management and Cost Optimisation",
    "Vessel IT Systems Support for VSAT, Bridge Systems and ECDIS Servers",
    "IT Service Desk and ITSM Operations",
    "Data Centre Operations and Disaster Recovery Management",
    "API Gateway and Integration Platform Management",
    "Digital Customer Platform Administration for Maersk.com",
]),
("IT", "CY", "Cybersecurity", "cybersecurity", [
    "Security Operations Centre Monitoring on Microsoft Sentinel",
    "Vulnerability Management and Patch Deployment",
    "Identity and Access Management with Azure AD, MFA and Zero-Trust",
    "Vessel Operational Technology Network Security",
    "Cyber Incident Response using the NotPetya Playbook",
    "Third-Party and Supply Chain Cyber Risk Assessment",
    "PCI DSS Compliance for Freight Payment Card Processing",
    "Employee Phishing Awareness and Security Culture Training",
]),
("PR", "SP", "Strategic Procurement", "strategic-procurement", [
    "Bunker Supplier Qualification and Approved Vendor List",
    "Ship Chandler and Port Agent Procurement and Management",
    "Dry Dock and Shipyard Tender and Contract Award",
    "Spare Parts Global Category Management",
    "Cargo Equipment Procurement and New Container Orders",
    "IT Hardware and Software Vendor Management",
    "Supplier Performance Monitoring and Scorecard",
    "Contract Lifecycle Management and Renewal Calendar",
]),
("PR", "OP", "Operational Procurement and Vessel Supply", "operational-procurement", [
    "Purchase Requisition to Purchase Order Cycle in SAP Ariba",
    "Ship Chandling and Provisions Ordering for Vessel Port Calls",
    "Spare Parts Requisition and Emergency Air Freight Delivery",
    "Port Agent Appointment and Disbursement Account Prefunding",
    "Goods Receipt and Three-Way Match at Vessel and Depot",
    "Vendor Invoice Exception and Price Variance Resolution",
    "Warehouse and Depot Consumables Replenishment",
    "Procurement Master Data and Material Catalogue Maintenance",
]),
("SU", "DC", "Decarbonisation and Emissions", "decarbonisation", [
    "CII Calculation and Rating Management",
    "EEXI Compliance and Energy Efficiency Technical File",
    "EU MRV and IMO DCS Emissions Data Collection and Reporting",
    "Green Methanol Procurement and Supply Chain Development",
    "Carbon Offset and Insetting Programme Management",
    "ECO Delivery Green Shipping Customer Product Management",
    "Science-Based Targets Commitment and Progress Reporting",
    "Sustainable Shipping Network Partnership and Industry Collaboration",
]),
("SU", "ES", "ESG Reporting and Circular Economy", "esg-reporting", [
    "CSRD and ESRS Sustainability Statement Preparation",
    "EU ETS Allowance Surrender and Carbon Cost Pass-Through",
    "Scope 1, 2 and 3 Greenhouse Gas Inventory Consolidation",
    "Ship Recycling and Hong Kong Convention Compliance",
    "Inventory of Hazardous Materials Maintenance",
    "Supplier ESG Screening and Responsible Sourcing Audit",
    "Ocean Health Programme Management for Whale Strike and Underwater Noise",
    "ESG Rating Agency Response and Investor Disclosure",
]),
("IM", "IN", "Intermodal Operations", "intermodal-operations", [
    "Port-to-Inland Rail Intermodal Booking with BNSF and Union Pacific",
    "Inland Container Depot Operations Management",
    "Drayage Carrier Management and Street Turn Optimisation",
    "US Customs Exam Coordination at Inland Port",
    "Last Mile Delivery Scheduling and Customer Notification",
    "White Glove Delivery and Room-of-Choice Service",
    "B2C Parcel and E-Commerce Last Mile Coordination",
    "Reverse Logistics and Returns Processing",
]),
("LG", "LI", "Legal and Insurance", "legal-insurance", [
    "P&I Club Claim Notification and Management",
    "Hull and Machinery Insurance Annual Renewal",
    "Cargo Claims Legal Defence and Settlement",
    "Charter Party Arbitration and Dispute Resolution under LMAA",
    "Vessel Arrest Prevention and Release Management",
    "Regulatory Penalty Response for PSC Detention and Flag State",
    "Contract Review for Service Agreements and Agency Agreements",
    "GDPR and Data Privacy Compliance Management",
]),
("LG", "RG", "Regulatory Affairs and Corporate Governance", "regulatory-affairs", [
    "Competition Law and Alliance Antitrust Compliance",
    "FMC and EU Consortia Block Exemption Filing Management",
    "Corporate Entity Governance and Subsidiary Board Administration",
    "Sanctions Legal Advisory and Vessel Screening Escalation",
    "Anti-Bribery and Facilitation Payment Compliance",
    "Litigation Hold, e-Discovery and Legal Case Management",
    "Trademark, Brand and Intellectual Property Protection",
    "Regulatory Horizon Scanning and Industry Body Engagement",
]),
]

EA_DIAGRAMS = [
    ("ea-01", "Shipping Enterprise System Landscape",
     "Full Maersk technology stack across all 16 domains including SAP S/4HANA, Navis N4, Veson IMOS and Microsoft Azure"),
    ("ea-02", "Cargo Journey Data Flow",
     "Booking through B/L, stowage, vessel, terminal, customs and final delivery"),
    ("ea-03", "Terminal Operations Architecture",
     "Gate, yard, crane and vessel flows across APM Terminals on Navis N4"),
    ("ea-04", "Integrated Logistics Platform Architecture",
     "Ocean, air via Senator, land via Pilot Freight and warehousing via LF Logistics convergence"),
    ("ea-05", "Customs and Trade Compliance Data Flow",
     "Shipper through customs broker, AES and ICS2 filing, duty payment and cargo release"),
    ("ea-06", "Fleet Management and Maintenance Architecture",
     "SHIPNET and Amos PMS through dry dock, class survey, Port State Control and SAP asset accounting"),
    ("ea-07", "Revenue Management and Pricing Architecture",
     "Market intelligence through rate setting, contract, booking and revenue recognition"),
    ("ea-08", "Sustainability and Decarbonisation Architecture",
     "CII and EEXI through MRV reporting, green methanol supply, SBTi targets and ECO Delivery"),
    ("ea-09", "Cybersecurity Architecture",
     "SOC and Azure Sentinel through OT security, vessel network segmentation and incident response"),
    ("ea-10", "Customer Digital Platform Architecture",
     "Maersk.com through API layer, Salesforce, track and trace, ECO Delivery and billing"),
]

EA_DIR_SLUG = "ea-diagrams"


def build_catalogue():
    """Return ordered list of process dicts."""
    out = []
    for l1, l2, l2_name, l2_slug, names in TAXONOMY:
        for i, name in enumerate(names, start=1):
            pid = f"{l1}-{l2}-{i:02d}"
            out.append({
                "pid":      pid,
                "slug":     pid.lower(),
                "l1":       l1,
                "l1_name":  L1_META[l1][1],
                "l1_icon":  L1_META[l1][0],
                "l1_slug":  L1_META[l1][2],
                "l2":       l2,
                "l2_name":  l2_name,
                "l2_slug":  l2_slug,
                "name":     name,
                "path":     f"{L1_META[l1][2]}/{l2_slug}/{pid.lower()}/index.html",
            })
    return out


PROCESSES = build_catalogue()
BY_PID    = {p["pid"]: p for p in PROCESSES}
assert len(PROCESSES) == 300, f"catalogue is {len(PROCESSES)} processes, expected 300"

# ─────────────────────────────────────────────────────────────────────────────
# MERMAID SANITISER  (battle-tested — do not modify)
# ─────────────────────────────────────────────────────────────────────────────

def sanitise_mermaid(mmd_str):
    if not mmd_str:
        return None
    import re
    # 1. Strip markdown fences
    mmd_str = re.sub(r'^```[a-z]*\n?', '', mmd_str, flags=re.MULTILINE)
    mmd_str = re.sub(r'```$', '', mmd_str, flags=re.MULTILINE)
    # 2. Remove YAML frontmatter
    mmd_str = re.sub(r'^---.*?---\s*', '', mmd_str, flags=re.DOTALL)
    # 3. Fix HTML-encoded arrows
    mmd_str = mmd_str.replace('--gt;', '-->').replace('--&gt;', '-->').replace('--&gt', '-->')
    # 3b. HTML line breaks would lose their angle brackets in step 5
    for _tag in ('<br/>', '<br />', '<br>'):
        mmd_str = mmd_str.replace(_tag, '\\n')
    # 4. Fix digit-start node IDs: 1.1 -> S1_1
    #    Label text is stashed first so real citations survive: MARPOL Annex 1.2,
    #    SOLAS 74.3 and ISO 9001.2015 must NOT be rewritten.
    stash = []

    def _hold(m):
        stash.append(m.group(0))
        return f'\x00{len(stash) - 1}\x00'

    mmd_str = re.sub(r'\[[^\]]*\]|\{[^}]*\}|\|"[^"]*"\|', _hold, mmd_str)
    mmd_str = re.sub(r'\b(\d+)\.(\d+)\b', r'S\1_\2', mmd_str)
    mmd_str = re.sub(r'\x00(\d+)\x00', lambda m: stash[int(m.group(1))], mmd_str)
    # 5. Remove special chars from inside node labels [ ], ( ) and { }
    def clean_label(m):
        text = m.group(2)
        text = re.sub(r'[()&<>]', '', text)
        text = re.sub(r'  +', ' ', text).strip()
        return f'{m.group(1)}{text}{m.group(3)}'
    mmd_str = re.sub(r'(\[)([^\]]+)(\])', clean_label, mmd_str)
    mmd_str = re.sub(r'(\{)([^}]+)(\})', clean_label, mmd_str)
    mmd_str = re.sub(r'(\()([^)]+)(\))', clean_label, mmd_str)
    # 6. Force one canonical %%{init}%%. Models emit init blocks with no fontFamily,
    #    and an SVG in an <img> tag cannot load webfonts — it silently falls back to
    #    a serif face, which is what makes rendered text look soft.
    mmd_str = re.sub(r'^\s*%%\{init.*?\}%%\s*\n?', '', mmd_str, flags=re.DOTALL | re.MULTILINE)
    mmd_str = INIT_LINE + "\n" + mmd_str.lstrip()
    # 7. Remove blank lines between %%{init}%% and flowchart directive
    lines = mmd_str.strip().split('\n')
    cleaned = []
    for line in lines:
        if cleaned and cleaned[-1].strip().startswith('%%{init') and line.strip() == '':
            continue
        cleaned.append(line)
    return '\n'.join(cleaned).strip()


# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────

def dump_raw(tag, raw):
    """Save an unparseable model response for inspection."""
    try:
        d = DATA_DIR / "raw"
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{tag}.txt"
        f.write_text(raw or "(empty response)", encoding="utf-8")
        log(f"  raw response saved to {f}", "WARN")
    except Exception:
        pass


def log(msg, level="INFO"):
    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp}] {level:<5} {msg}", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# OLLAMA
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT_JSON = """You are a senior SAP consultant and maritime industry expert with deep knowledge of:
- A.P. Moller-Maersk A/S operations across ocean shipping, logistics and terminal management
- Global container shipping including alliances, vessel operations and port operations
- Maritime regulation: IMO, SOLAS, MARPOL, ISM Code, MLC 2006, ISPS Code
- The post-NotPetya IT transformation at Maersk on Microsoft Azure and SAP S/4HANA

Key systems: SAP S/4HANA ERP, Navis N4 TOS at APM Terminals, Veson Nautical IMOS voyage
management, SHIPNET and Amos ABB planned maintenance, CargOPTIMIZER stowage planning,
CargoSphere rate management, Salesforce CRM, Maersk.com digital booking platform,
Manhattan Associates WMS, Senator International TMS for air freight, Microsoft Azure,
Power BI, Workday HCM for shore staff, COMPAS and OSCAR seafarer crewing, Synergi Life HSSE,
MarineTraffic AIS vessel tracking, DNV and Lloyd's Register classification, Skuld P&I Club,
Descartes and MIC Customs for customs brokerage, Maersk Remote Container Management.

Reference operation: Maersk Line, the ocean carrier arm of A.P. Moller-Maersk.
Reference vessel: Triple-E class, 400m, 24,000 TEU, plus standard Maersk fleet.

Return ONLY valid JSON with no markdown fences, no preamble, no trailing text and
absolutely no Mermaid or diagram syntax anywhere in the response."""

MERMAID_RULES = """MERMAID CRITICAL RULES (violations cause mmdc parse errors):
- Line 1 MUST be: %%{init: {'theme':'base','themeVariables':{'fontSize':'12px'}}}%%
- NO YAML frontmatter
- Node IDs MUST start with a LETTER such as NodeA, StepB or S1_1 — never a digit
- Arrows are ALWAYS --> and never --gt or --&gt;
- Node labels contain NO parentheses, no ampersand, no angle brackets"""

SYSTEM_PROMPT = SYSTEM_PROMPT_JSON + "\n\n" + MERMAID_RULES

JSON_SHAPE = """{
  "description": "2-3 sentence operational description in the Maersk context",
  "trigger": "what initiates this process",
  "outcome": "what successful completion produces",
  "l4_steps": [
    {
      "step": "1.1",
      "name": "Step name",
      "role": "Exact maritime role such as Vessel Master, Port Captain, Cargo Planner",
      "system": "Exact system such as Navis N4, Veson Nautical IMOS, SAP S/4HANA",
      "input": "Input document or data",
      "output": "Output document or deliverable",
      "kpi": "Measurable metric with target",
      "decision_point": "Y or N",
      "exception": "Y or N",
      "pain_point": "Real maritime or logistics operational challenge at this step"
    }
  ],
  "swim_lanes": [{"role": "Role Title", "color": "#hex", "steps": ["1.1", "1.2"]}],
  "systems": ["Navis N4", "SAP S/4HANA"],
  "kpis": ["Crane moves per hour above 30", "VGM filing compliance 100 percent"],
  "risks": ["Hazmat misdeclaration causing vessel fire risk"]
}"""

CONTENT_RULES = """CONTENT RULES:
- 10 to 12 l4_steps spread across 3 phases
- At least 3 steps must be genuine decision points with decision_point Y
- At least 2 steps must have exception Y
- Real Maersk and maritime roles: Vessel Master, Chief Officer, Port Captain, Cargo Planner,
  Customs Broker, Freight Coordinator, Claims Handler, Operations Manager, Trade Lane Manager
- 4 to 6 real systems per process
- 4 to 6 KPIs with measurable targets
- 3 to 5 maritime-specific risks covering regulatory, safety, commercial and operational
- Do NOT include a mermaid field. The diagram is requested separately.
- JSON ONLY — no markdown, no preamble"""


# Form reference for the BPMN diagram. Airline content on purpose, so the model
# copies the CONSTRUCT and never the subject matter.
BPMN_FORM_EXAMPLE = """flowchart LR
  subgraph P1[Phase 1: Request and Screening]
    A([Start]) --> B[Receive crew requisition\\nSuccessFactors]
    B --> C{Gap above\\nrecruitment threshold?}
    C -- No --> B
    C -- Yes --> D[Publish vacancy and\\nbuild candidate pipeline]
  end

  subgraph P2[Phase 2: Assessment]
    D --> E[Screen against\\nFAR 121 ATP minimums]
    E --> F{Meets minimums?}
    F -- No --> Rej1([Decline])
    F -- Yes --> G[Simulator assessment\\nFFS Level D]
    G --> H{Sim result\\npass or fail?}
    H -- Fail --> Rej1
  end

  subgraph P3[Phase 3: Clearance and Offer]
    H -- Pass --> I[Background and\\nmedical screening]
    I --> J{All clearances\\nreceived?}
    J -- No --> Hold1([Hold])
    J -- Yes --> K[Issue contract and\\nconfirm class date]
    K --> L([End])
  end

  style A fill:#002b5c,color:#fff,stroke:#002b5c
  style L fill:#002b5c,color:#fff,stroke:#002b5c
  style Rej1 fill:#002b5c,color:#fff,stroke:#002b5c
  style Hold1 fill:#002b5c,color:#fff,stroke:#002b5c
  style C fill:#42b0d5,color:#fff,stroke:#42b0d5
  style F fill:#42b0d5,color:#fff,stroke:#42b0d5
  style H fill:#42b0d5,color:#fff,stroke:#42b0d5
  style J fill:#42b0d5,color:#fff,stroke:#42b0d5"""


def ollama_call(prompt, model, temperature=0.35):
    r = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model":  model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_ctx": 8192},
        },
        timeout=OLLAMA_TIMEOUT,
    )
    r.raise_for_status()
    return r.json().get("response", "")


def extract_json(raw, required=None):
    """Find the first balanced object that parses AND carries the expected keys.

    Small models often prepend a Mermaid block; its %%{init: {...}}%% braces are the
    first thing a naive scanner finds, so those are stripped before scanning and every
    remaining candidate is tried in turn.
    """
    if not raw:
        return None
    text = re.sub(r'^```[a-z]*\n?', '', raw.strip(), flags=re.MULTILINE)
    text = re.sub(r'```$', '', text, flags=re.MULTILINE)
    text = re.sub(r'%%\{.*?\}%%', '', text, flags=re.DOTALL)      # mermaid init blocks
    text = re.sub(r'^\s*(flowchart|graph)\s+\w+.*$', '', text, flags=re.MULTILINE)

    def candidates(s):
        depth = start = 0
        in_str = esc = False
        for i, ch in enumerate(s):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                if depth:
                    depth -= 1
                    if depth == 0:
                        yield s[start:i + 1]

    best = None
    for blob in candidates(text):
        for attempt in (blob, blob.replace("\n", " "), re.sub(r',\s*([}\]])', r'\1', blob)):
            try:
                data = json.loads(attempt)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                break
            if required and not any(data.get(k) for k in required):
                best = best or data
                break
            return data
    return best


def generate_process_content(proc, attempt=0):
    """Ask Ollama for the process JSON. Falls back to the secondary model."""
    prompt = (
        f"{SYSTEM_PROMPT_JSON}\n\n"
        f"Document this business process for A.P. Moller-Maersk:\n"
        f"  Process ID : {proc['pid']}\n"
        f"  L1 Domain  : {proc['l1_name']}\n"
        f"  L2 Group   : {proc['l2_name']}\n"
        f"  L3 Process : {proc['name']}\n\n"
        f"Return exactly this JSON shape:\n{JSON_SHAPE}\n\n{CONTENT_RULES}\n"
    )
    models = [PRIMARY_MODEL, PRIMARY_MODEL, FALLBACK_MODEL]
    for i, model in enumerate(models):
        try:
            raw = ollama_call(prompt, model, temperature=0.3 + 0.1 * i)
            data = extract_json(raw, required=("l4_steps",))
            if not data:
                dump_raw(f"{proc['pid']}-json-{i+1}", raw)
            if data and data.get("l4_steps"):
                data.setdefault("systems", [])
                data.setdefault("kpis", [])
                data.setdefault("risks", [])
                return data
            log(f"{proc['pid']}: unusable JSON from {model} (try {i+1}/3)", "WARN")
        except Exception as exc:
            log(f"{proc['pid']}: Ollama error on {model} — {exc}", "WARN")
        time.sleep(2)
    return None


def generate_process_mermaid(proc, data, attempt=0):
    """Second call, raw Mermaid only — no JSON, so no escaping games with \\n."""
    steps = "\n".join(
        f"  {s.get('step','')} {s.get('name','')} "
        f"[role: {s.get('role','')} | system: {s.get('system','')} | "
        f"decision: {s.get('decision_point','N')} | exception: {s.get('exception','N')}]"
        for s in data.get("l4_steps", [])
    )
    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Draw the BPMN process flow for Maersk process {proc['pid']} — {proc['name']}\n"
        f"in the {proc['l1_name']} domain.\n\n"
        f"These are the L4 steps it must cover:\n{steps}\n\n"
        "STRUCTURE — copy this construct exactly. It is from a different industry, so take\n"
        "the FORM and none of the content:\n\n"
        f"{BPMN_FORM_EXAMPLE}\n\n"
        "REQUIREMENTS:\n"
        "- flowchart LR with 5 or 6 phase subgraphs named P1 to P6, each titled\n"
        "  Phase N: short phase name.\n"
        "- One ([Start]) terminator and one ([End]) terminator. Add 1 or 2 more terminators\n"
        "  for exception exits such as ([Reject]), ([Hold]) or ([Escalate]).\n"
        "- 5 to 8 decision diamonds using curly braces. EVERY decision has at least two\n"
        "  labelled outbound branches written as X -- Yes --> Y and X -- No --> Z.\n"
        "  Use real maritime decision language: VGM received, DG approved, PSC deficiency\n"
        "  raised, customs hold, cut-off met.\n"
        "- At least 2 rework loops that route a failed decision BACK to an earlier task node\n"
        "  rather than straight to an exit. This is what makes the flow multi-path.\n"
        "- 22 to 30 nodes overall. Every task label is two lines: what happens, then a\n"
        "  literal backslash-n, then the system or document involved.\n"
        "  Example: VGM[Verify gross mass declaration\\\\nNavis N4 and shipper VGM feed]\n"
        "- Flow must cross subgraph boundaries: a node in P2 connects to nodes in P3 and,\n"
        "  where there is rework, back to P1.\n"
        "- Close with style lines. Terminators fill:#002b5c,color:#fff,stroke:#002b5c and\n"
        "  every decision diamond fill:#42b0d5,color:#fff,stroke:#42b0d5.\n"
        "- Node IDs start with a letter. No parentheses, ampersands or angle brackets inside\n"
        "  any label. Never use <br/>. Arrows are --> only.\n\n"
        "Output the raw Mermaid and nothing else. No JSON, no fences, no commentary.\n"
    )
    models = [PRIMARY_MODEL, PRIMARY_MODEL, FALLBACK_MODEL]
    model = models[min(attempt, len(models) - 1)]
    try:
        return sanitise_mermaid(ollama_call(prompt, model, temperature=0.2 + 0.1 * attempt))
    except Exception as exc:
        log(f"{proc['pid']}: mermaid call failed on {model} — {exc}", "WARN")
        return None


def diagram_richness(mmd):
    """Cheap structural score so a thin diagram gets retried, not published."""
    if not mmd:
        return 0, {}
    m = {
        "nodes":     len(re.findall(r'^\s*\w+[\[\({]', mmd, flags=re.MULTILINE)),
        "decisions": len(re.findall(r'\w+\{[^}]+\}', mmd)),
        "branches":  len(re.findall(r'--\s*[A-Za-z][\w \-]*\s*-->', mmd)),
        "subgraphs": mmd.count("subgraph"),
        "styles":    len(re.findall(r'^\s*style\s', mmd, flags=re.MULTILINE)),
    }
    score = (m["decisions"] >= 4) + (m["branches"] >= 6) + (m["subgraphs"] >= 4) \
            + (m["styles"] >= 4) + (m["nodes"] >= 18)
    return score, m


# ─────────────────────────────────────────────────────────────────────────────
# MMDC RENDERING
# ─────────────────────────────────────────────────────────────────────────────

def render_mermaid(mmd_text, mmd_path, out_path, width, height, scale=MMDC_SCALE):
    """Render to whatever extension out_path carries — .svg stays sharp at any zoom."""
    mmd_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mmd_path.write_text(mmd_text, encoding="utf-8")
    is_svg = out_path.suffix.lower() == ".svg"
    cmd = [
        "mmdc", "-i", str(mmd_path), "-o", str(out_path),
        "-w", str(width), "-H", str(height), "--backgroundColor", "white",
    ]
    if not is_svg:
        cmd += ["--scale", str(scale)]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return False, "mmdc timed out"
    if res.returncode != 0:
        return False, (res.stderr or res.stdout or "mmdc failed").strip()[:400]
    floor = 1024 if is_svg else 4096
    if not out_path.exists() or out_path.stat().st_size < floor:
        return False, f"mmdc produced no usable {out_path.suffix.lstrip('.')}"
    size_mb = out_path.stat().st_size / (1024 * 1024)
    if not is_svg and size_mb > 90 and scale > 1:
        log(f"{out_path.name}: {size_mb:.1f}MB — re-rendering at lower scale", "WARN")
        return render_mermaid(mmd_text, mmd_path, out_path, int(width * 0.75),
                              int(height * 0.75), scale=scale - 1)
    return True, f"{size_mb:.2f}MB"


def finalize_svg(path):
    """mmdc emits width="100%" plus an inline max-width on the root <svg>.

    Both are hostile to zooming: the max-width caps how large the vector will
    ever render, so the browser rasterises at that ceiling and scales the bitmap
    up — which looks exactly like a blurry PNG. Replacing them with the viewBox
    dimensions gives the file a real intrinsic size and no ceiling.
    """
    try:
        svg = path.read_text(encoding="utf-8")
    except Exception:
        return False
    m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    if not m:
        return False
    w, h = m.group(1), m.group(2)
    svg = svg.replace('width="100%"', f'width="{w}" height="{h}"', 1)
    svg = re.sub(r'max-width:\s*[\d.]+px;?\s*', '', svg, count=1)
    if 'height=' not in svg.split('>', 1)[0]:
        svg = svg.replace('<svg ', f'<svg height="{h}" ', 1)
    path.write_text(svg, encoding="utf-8")
    log(f"  svg finalised — intrinsic {w}x{h}, size cap removed")
    return True


def build_diagram(proc, data, kind="pid"):
    """Generate, score, sanitise and render. 3 attempts. Returns png Path or None."""
    mmd_path = DIAGRAM_DIR / f"{proc['slug']}.mmd"
    svg_path = IMG_DIR / f"{proc['slug']}.svg"
    best, best_score = None, -1

    for attempt in range(3):
        candidate = generate_process_mermaid(proc, data, attempt=attempt)
        score, metrics = diagram_richness(candidate)
        if candidate and score > best_score:
            best, best_score = candidate, score
        log(f"  diagram draft {attempt+1}: score {score}/5 {metrics}")
        if score >= 4:
            break

    if not best:
        return None
    if best_score < 3:
        log(f"  {proc['pid']}: diagram is thin (score {best_score}/5) — publishing anyway, "
            f"re-run with --pid {proc['pid']} to try again", "WARN")

    for attempt in range(1, 4):
        ok, info = render_mermaid(best, mmd_path, svg_path, PID_W, PID_H)
        if ok:
            finalize_svg(svg_path)
            log(f"  diagram rendered as SVG ({info}) on render attempt {attempt}")
            return svg_path
        log(f"  mmdc attempt {attempt}/3 failed: {info}", "WARN")
        retry = generate_process_mermaid(proc, data, attempt=attempt)
        if retry:
            best = retry
    return None


# ─────────────────────────────────────────────────────────────────────────────
# GITHUB
# ─────────────────────────────────────────────────────────────────────────────

def _make_session():
    s = requests.Session()
    retry = Retry(total=5, backoff_factor=2, status_forcelist=[500, 502, 503, 504],
                  allowed_methods=["GET", "PUT", "POST"])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


GH_SESSION = _make_session()


def gh_headers():
    if not GITHUB_TOKEN:
        sys.exit("GITHUB_TOKEN is not set. Run: export GITHUB_TOKEN=your_new_token")
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def gh_get_sha(repo_path):
    try:
        r = GH_SESSION.get(f"{GH_API}/{repo_path}", headers=gh_headers(),
                           params={"ref": BRANCH}, timeout=60)
        if r.status_code == 200:
            return r.json().get("sha")
    except Exception:
        pass
    return None


def gh_push_file(repo_path, content, message=None):
    """Push text or bytes. 4 attempts, 2/4/8/16s backoff. SHA fetched before every PUT."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    payload_b64 = b64encode(content).decode("ascii")
    msg = message or f"Update {repo_path}"

    for attempt in range(1, 5):
        try:
            body = {"message": msg, "content": payload_b64, "branch": BRANCH}
            sha = gh_get_sha(repo_path)
            if sha:
                body["sha"] = sha
            r = GH_SESSION.put(f"{GH_API}/{repo_path}", headers=gh_headers(),
                               json=body, timeout=120)
            if r.status_code in (200, 201):
                return True
            log(f"  push {repo_path} → HTTP {r.status_code} {r.text[:180]}", "WARN")
        except Exception as exc:
            log(f"  push {repo_path} error: {exc}", "WARN")
        time.sleep(2 ** attempt)
    log(f"  GAVE UP pushing {repo_path}", "ERROR")
    return False


def push_deploy():
    stamp = datetime.now().isoformat(timespec="seconds")
    ok = gh_push_file(".deploy", f"deploy {stamp}\n", f"Deploy {stamp}")
    log("`.deploy` pushed — Pages rebuild triggered" if ok else "`.deploy` push failed",
        "INFO" if ok else "ERROR")
    return ok


def verify_live(url, wait=VERIFY_WAIT):
    log(f"  waiting {wait}s for Pages build …")
    time.sleep(wait)
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=45)
            if r.status_code == 200 and "assets/img" in r.text:
                return True
            log(f"  verify attempt {attempt+1}: HTTP {r.status_code}", "WARN")
        except Exception as exc:
            log(f"  verify attempt {attempt+1} error: {exc}", "WARN")
        time.sleep(20)
    return False


# ─────────────────────────────────────────────────────────────────────────────
# LOCAL TRACKER  (never pushed to GitHub)
# ─────────────────────────────────────────────────────────────────────────────

def load_tracker():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if TRACKER.exists():
        try:
            return json.loads(TRACKER.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log("processes.json unreadable — starting a fresh tracker", "WARN")
    return {}


def save_tracker(tr):
    TRACKER.write_text(json.dumps(tr, indent=2), encoding="utf-8")


def is_complete(pid, tr):
    return tr.get(pid, {}).get("status") == "Complete"


def mark_complete(pid, tr, url):
    tr[pid] = {"status": "Complete", "url": url,
               "completed_at": datetime.now().isoformat(timespec="seconds")}
    save_tracker(tr)


def sync_tracker_from_github(tr):
    """If verification is unreliable, trust the repo tree instead."""
    try:
        r = GH_SESSION.get(
            f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/git/trees/{BRANCH}",
            headers=gh_headers(), params={"recursive": "1"}, timeout=120)
        if r.status_code != 200:
            return tr
        paths = {item["path"] for item in r.json().get("tree", [])}
        added = 0
        for p in PROCESSES:
            if p["path"] in paths and not is_complete(p["pid"], tr):
                tr[p["pid"]] = {"status": "Complete",
                                "url": f"{PAGES_BASE}/{p['path']}",
                                "completed_at": "synced-from-github"}
                added += 1
        if added:
            save_tracker(tr)
            log(f"tracker synced from GitHub — {added} process(es) marked complete")
    except Exception as exc:
        log(f"tree sync failed: {exc}", "WARN")
    return tr


# ─────────────────────────────────────────────────────────────────────────────
# EXCEL  (local only, written only after a successful verify)
# ─────────────────────────────────────────────────────────────────────────────

def ensure_excel():
    from openpyxl import Workbook, load_workbook
    if EXCEL_PATH.exists():
        return load_workbook(EXCEL_PATH)
    wb = Workbook()
    idx = wb.active
    idx.title = "Index"
    idx.append(["PID", "Process Name", "L1 Domain", "L2 Group",
                "Status", "GitHub Pages URL", "Completed At"])
    for p in PROCESSES:
        idx.append([p["pid"], p["name"], p["l1_name"], p["l2_name"],
                    "Queued", f"{PAGES_BASE}/{p['path']}", ""])
    cat = wb.create_sheet("Master Catalog")
    cat.append(["PID", "Step", "Step Name", "Role", "System", "Input", "Output",
                "KPI", "Decision", "Exception", "Pain Point"])
    wb.save(EXCEL_PATH)
    log(f"created {EXCEL_PATH.name}")
    return wb


def excel_record(proc, data, url):
    from openpyxl.utils import get_column_letter
    wb = ensure_excel()

    idx = wb["Index"]
    for row in idx.iter_rows(min_row=2):
        if row[0].value == proc["pid"]:
            row[4].value = "Complete"
            row[6].value = datetime.now().strftime("%Y-%m-%d %H:%M")
            break

    cat = wb["Master Catalog"]
    for s in data.get("l4_steps", []):
        cat.append([proc["pid"], s.get("step", ""), s.get("name", ""), s.get("role", ""),
                    s.get("system", ""), s.get("input", ""), s.get("output", ""),
                    s.get("kpi", ""), s.get("decision_point", "N"),
                    s.get("exception", "N"), s.get("pain_point", "")])

    tab = proc["pid"][:31]
    if tab in wb.sheetnames:
        del wb[tab]
    ws = wb.create_sheet(tab)
    ws.append(["Process ID", proc["pid"]])
    ws.append(["Process Name", proc["name"]])
    ws.append(["L1 Domain", proc["l1_name"]])
    ws.append(["L2 Group", proc["l2_name"]])
    ws.append(["Trigger", data.get("trigger", "")])
    ws.append(["Outcome", data.get("outcome", "")])
    ws.append(["Description", data.get("description", "")])
    ws.append(["Systems", ", ".join(data.get("systems", []))])
    ws.append(["KPIs", " | ".join(data.get("kpis", []))])
    ws.append(["Risks", " | ".join(data.get("risks", []))])
    ws.append(["URL", url])
    ws.append([])
    ws.append(["Step", "Name", "Role", "System", "Input", "Output",
               "KPI", "Decision", "Exception", "Pain Point"])
    for s in data.get("l4_steps", []):
        ws.append([s.get("step", ""), s.get("name", ""), s.get("role", ""),
                   s.get("system", ""), s.get("input", ""), s.get("output", ""),
                   s.get("kpi", ""), s.get("decision_point", "N"),
                   s.get("exception", "N"), s.get("pain_point", "")])
    for col, width in enumerate([10, 34, 26, 24, 26, 26, 30, 10, 10, 40], start=1):
        ws.column_dimensions[get_column_letter(col)].width = width

    wb.save(EXCEL_PATH)

# ─────────────────────────────────────────────────────────────────────────────
# HTML BUILDING
# ─────────────────────────────────────────────────────────────────────────────

import html as _html

# Domain families drive the sidebar dot and the PID badge colour
FAMILY = {
    "VO": "ops",  "CM": "ops",  "FM": "ops",  "HS": "ops",
    "FF": "flow", "CD": "flow", "SC": "flow", "IM": "flow",
    "RM": "comm", "CS": "comm",
    "HR": "corp", "FN": "corp", "IT": "corp",
    "PR": "corp", "SU": "corp", "LG": "corp",
}
FAMILY_LABEL = {"ops": "OPERATIONS", "flow": "CARGO FLOW",
                "comm": "COMMERCIAL", "corp": "CORPORATE"}

# Depth of each page type below the site root
DEPTH_PROCESS = 3      # l1/l2/pid/index.html
DEPTH_L2      = 2      # l1/l2/index.html
DEPTH_L1      = 1      # l1/index.html
DEPTH_EA      = 2      # ea-diagrams/ea-NN/index.html
DEPTH_EA_IDX  = 1      # ea-diagrams/index.html
DEPTH_ROOT    = 0      # index.html

SYS_TAG_MAP = [
    ("navis",              "navis-n4"),
    ("cargoptimizer",      "cargo-opt"),
    ("cargosphere",        "cargosphere"),
    ("sap ariba",          "ariba"),
    ("ariba",              "ariba"),
    ("sap",                "sap"),
    ("veson",              "veson"),
    ("imos",               "veson"),
    ("shipnet",            "shipnet"),
    ("amos",               "shipnet"),
    ("salesforce",         "salesforce"),
    ("azure",              "azure"),
    ("sentinel",           "azure"),
    ("workday",            "workday"),
    ("manhattan",          "manhattan"),
    ("senator",            "senator"),
    ("pilot freight",      "pilot-fr"),
    ("maersk.com",         "maersk-com"),
    ("maersk spot",        "maersk-com"),
    ("track and trace",    "maersk-com"),
    ("navtor",             "navtor"),
    ("napa",               "navtor"),
    ("descartes",          "descartes"),
    ("mic customs",        "descartes"),
    ("power bi",           "powerbi"),
    ("powerbi",            "powerbi"),
    ("remote container",   "rcm"),
    ("rcm",                "rcm"),
    ("synergi",            "synergi"),
    ("maims",              "synergi"),
    ("compas",             "compas"),
    ("oscar",              "compas"),
    ("ecdis",              "ecdis"),
    ("marinetraffic",      "marinetraf"),
    ("ais",                "marinetraf"),
    ("dnv",                "dnv"),
    ("lloyd",              "dnv"),
    ("skuld",              "skuld"),
    ("p&i",                "skuld"),
    ("servicenow",         "servicenow"),
    ("mulesoft",           "azure"),
]


def sys_tag_class(name):
    low = (name or "").lower()
    for needle, cls in SYS_TAG_MAP:
        if needle in low:
            return cls
    return "custom"


def sys_tags(systems):
    out = []
    for s in systems or []:
        s = str(s).strip()
        if not s or s.lower() in ("none", "n/a"):
            continue
        out.append(f'<span class="sys-tag {sys_tag_class(s)}">{esc(s)}</span>')
    return " ".join(out) or '<span class="sys-tag custom">Not specified</span>'


def esc(text):
    return _html.escape(str(text if text is not None else ""), quote=False)


def prefix(depth):
    return "../" * depth if depth else "./"


def trunc(text, n=52):
    text = str(text)
    return text if len(text) <= n else text[: n - 1].rstrip() + "\u2026"


# ── Sidebar (static HTML, baked into every page) ─────────────────────────────

def build_sidebar(depth, active_pid=None, active_ea=None):
    """Full navigation: every L1, every L2, every process, plus the EA section."""
    p = prefix(depth)
    active = BY_PID.get(active_pid) if active_pid else None
    parts = ['<nav class="wiki-nav">']

    for l1_code, (icon, l1_name, l1_slug) in L1_META.items():
        groups = [g for g in TAXONOMY if g[0] == l1_code]
        open_l1 = " open" if active and active["l1"] == l1_code else ""
        fam = FAMILY[l1_code]
        parts.append(f'<div class="nav-domain{open_l1}">')
        parts.append(
            f'  <a class="nav-l1" href="{p}{l1_slug}/index.html">'
            f'<span class="nav-l1-icon">{icon}</span>'
            f'<span class="nav-org-dot {fam}"></span>'
            f'<span class="nav-l1-text">{esc(l1_name)}</span>'
            f'<span class="nav-l1-caret">&#9654;</span></a>'
        )
        parts.append('  <div class="nav-l2-list">')
        for _, l2_code, l2_name, l2_slug, names in groups:
            open_l2 = " open" if active and active["l1"] == l1_code and active["l2"] == l2_code else ""
            parts.append(f'    <div class="nav-l2-group{open_l2}">')
            parts.append(
                f'      <a class="nav-l2-title" href="{p}{l1_slug}/{l2_slug}/index.html">'
                f'{esc(l2_name)}</a>'
            )
            parts.append('      <div class="nav-l3-list">')
            for i, name in enumerate(names, start=1):
                pid = f"{l1_code}-{l2_code}-{i:02d}"
                cls = "nav-l3 active" if pid == active_pid else "nav-l3"
                parts.append(
                    f'        <a class="{cls}" '
                    f'href="{p}{l1_slug}/{l2_slug}/{pid.lower()}/index.html">'
                    f'{pid} &mdash; {esc(trunc(name))}</a>'
                )
            parts.append('      </div>')
            parts.append('    </div>')
        parts.append('  </div>')
        parts.append('</div>')

    # EA section — its own domain block, always open on EA pages
    open_ea = " open" if active_ea else ""
    parts.append(f'<div class="nav-domain{open_ea}">')
    parts.append(
        f'  <a class="nav-l1" href="{p}{EA_DIR_SLUG}/index.html">'
        f'<span class="nav-l1-icon">\U0001F5FA</span>'
        f'<span class="nav-org-dot corp"></span>'
        f'<span class="nav-l1-text">Enterprise Architecture</span>'
        f'<span class="nav-l1-caret">&#9654;</span></a>'
    )
    parts.append('  <div class="nav-l2-list">')
    parts.append(f'    <div class="nav-l2-group{open_ea}">')
    parts.append(f'      <a class="nav-l2-title" href="{p}{EA_DIR_SLUG}/index.html">EA Diagrams</a>')
    parts.append('      <div class="nav-l3-list">')
    for ea_id, ea_title, _ in EA_DIAGRAMS:
        cls = "nav-l3 active" if ea_id == active_ea else "nav-l3"
        parts.append(
            f'        <a class="{cls}" href="{p}{EA_DIR_SLUG}/{ea_id}/index.html">'
            f'{ea_id.upper()} &mdash; {esc(trunc(ea_title))}</a>'
        )
    parts.append('      </div>')
    parts.append('    </div>')
    parts.append('  </div>')
    parts.append('</div>')
    parts.append('</nav>')
    return "\n".join(parts)


def page_shell(title, topbar_sub, depth, main_html, active_pid=None, active_ea=None):
    p = prefix(depth)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} &mdash; {SITE_TITLE}</title>
  <link rel="stylesheet" href="{p}assets/css/wiki.css">
</head>
<body>
  <div class="topbar">
    <button id="topbarToggle" aria-label="Menu"><span></span><span></span><span></span></button>
    <a class="topbar-brand" href="{p}index.html">{SITE_TITLE}</a>
    <span class="topbar-sub">{topbar_sub}</span>
    <span class="topbar-spacer"></span>
  </div>
  <div class="wiki-layout">
    <nav id="sidebar">
      <button id="sidebarToggle" title="Collapse sidebar">&#9664;</button>
{build_sidebar(depth, active_pid, active_ea)}
    </nav>
    <main class="wiki-main">
{main_html}
    </main>
  </div>
  <div id="lightbox"><img id="lightboxImg" src="" alt=""></div>
  <script src="{p}assets/js/wiki.js"></script>
</body>
</html>
"""


# ── Process page ─────────────────────────────────────────────────────────────

def build_process_page(proc, data):
    p = prefix(DEPTH_PROCESS)
    fam = FAMILY[proc["l1"]]
    rows = []
    for s in data.get("l4_steps", []):
        dec = ('<span class="decision-y">Y</span>'
               if str(s.get("decision_point", "N")).upper().startswith("Y") else "N")
        exc = ('<span class="exception-y">Y</span>'
               if str(s.get("exception", "N")).upper().startswith("Y") else "N")
        rows.append(f"""        <tr>
          <td class="step-num">{esc(s.get('step',''))}</td>
          <td>{esc(s.get('name',''))}</td>
          <td>{esc(s.get('role',''))}</td>
          <td><span class="sys-tag {sys_tag_class(s.get('system'))}">{esc(s.get('system',''))}</span></td>
          <td>{esc(s.get('input',''))}</td>
          <td>{esc(s.get('output',''))}</td>
          <td>{esc(s.get('kpi',''))}</td>
          <td>{esc(s.get('pain_point',''))}</td>
          <td>{dec}</td>
          <td>{exc}</td>
        </tr>""")

    kpis = " ".join(f'<span class="kpi-pill">{esc(k)}</span>' for k in data.get("kpis", []))
    risks = " ".join(f'<span class="risk-pill">{esc(r)}</span>' for r in data.get("risks", []))
    lanes = " ".join(
        f'<span class="kpi-pill" style="background:#e2e8f0;color:#334155">'
        f'{esc(l.get("role",""))} &middot; {esc(", ".join(l.get("steps", [])))}</span>'
        for l in data.get("swim_lanes", []) if isinstance(l, dict)
    )

    main = f"""      <div class="page-header">
        <div class="breadcrumb">
          <a href="{p}index.html">Home</a> &rsaquo;
          <a href="{p}{proc['l1_slug']}/index.html">{esc(proc['l1_name'])}</a> &rsaquo;
          <a href="{p}{proc['l1_slug']}/{proc['l2_slug']}/index.html">{esc(proc['l2_name'])}</a>
        </div>
        <h1>
          <span class="pid-badge org-badge-{fam}">{proc['l1']}</span>
          {proc['pid']} &mdash; {esc(proc['name'])}
        </h1>
        <p>{esc(data.get('description',''))}</p>
      </div>

      <div class="card">
        <div class="card-header">&#x1F5FA; BPMN Process Flow</div>
        <div class="card-body">
          <div class="diagram-wrap">
            <a href="{p}assets/img/{proc['slug']}.svg" data-lightbox data-title="{proc['pid']} BPMN">
              <img src="{p}assets/img/{proc['slug']}.svg" alt="{proc['pid']} BPMN Diagram">
            </a>
            <p>Click diagram to zoom &amp; pan &bull; Scroll to zoom &bull; Drag to pan &bull;
               <a href="{p}assets/img/{proc['slug']}.svg" download>Download SVG</a></p>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">&#x1F4CB; Process Attributes</div>
        <div class="card-body">
          <table class="attr-table">
            <tr><th>Process ID</th><td>{proc['pid']}</td></tr>
            <tr><th>Domain Family</th><td>{FAMILY_LABEL[fam]}</td></tr>
            <tr><th>L1 Domain</th><td>{esc(proc['l1_name'])}</td></tr>
            <tr><th>L2 Process Group</th><td>{esc(proc['l2_name'])}</td></tr>
            <tr><th>L3 Name</th><td>{esc(proc['name'])}</td></tr>
            <tr><th>Trigger</th><td>{esc(data.get('trigger',''))}</td></tr>
            <tr><th>Outcome</th><td>{esc(data.get('outcome',''))}</td></tr>
            <tr><th>Systems</th><td>{sys_tags(data.get('systems'))}</td></tr>
          </table>
        </div>
      </div>

      <div class="card">
        <div class="card-header">&#x1F4CB; L4 Process Steps</div>
        <div class="card-body">
          <div class="l4-table-wrap">
            <table class="l4-table">
              <thead>
                <tr>
                  <th>Step</th><th>Name</th><th>Role</th><th>System</th>
                  <th>Input</th><th>Output</th><th>KPI</th><th>Pain Point / Risk</th>
                  <th>Decision?</th><th>Exception?</th>
                </tr>
              </thead>
              <tbody>
{chr(10).join(rows)}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">&#x1F4CA; KPIs &amp; Risk Register</div>
        <div class="card-body">
          <p class="mb-8"><strong>KPIs</strong></p>
          <div class="kpi-list mb-8">{kpis or '<span class="text-muted">None captured</span>'}</div>
          <p class="mb-8" style="margin-top:16px"><strong>Key Risks</strong></p>
          <div class="kpi-list">{risks or '<span class="text-muted">None captured</span>'}</div>
          {'<p class="mb-8" style="margin-top:16px"><strong>Swim Lanes</strong></p><div class="kpi-list">' + lanes + '</div>' if lanes else ''}
        </div>
      </div>
"""
    return page_shell(f"{proc['pid']} &mdash; {esc(proc['name'])}",
                      f"{esc(proc['l1_name'])} &rsaquo; {esc(proc['l2_name'])}",
                      DEPTH_PROCESS, main, active_pid=proc["pid"])


# ── Index pages ──────────────────────────────────────────────────────────────

def group_processes(l1_code, l2_code):
    return [p for p in PROCESSES if p["l1"] == l1_code and p["l2"] == l2_code]


def status_cell(pid, tr):
    if is_complete(pid, tr):
        return '<span style="color:#16a34a;font-weight:700">&#x2705; Complete</span>'
    return '<span style="color:#94a3b8">Queued</span>'


def build_l2_index(l1_code, l2_code, tr):
    icon, l1_name, l1_slug = L1_META[l1_code]
    group = next(g for g in TAXONOMY if g[0] == l1_code and g[1] == l2_code)
    l2_name, l2_slug = group[2], group[3]
    procs = group_processes(l1_code, l2_code)
    done = sum(1 for p in procs if is_complete(p["pid"], tr))
    p = prefix(DEPTH_L2)

    rows = "\n".join(
        f'<tr><td><a href="{x["slug"]}/index.html">{x["pid"]}</a></td>'
        f'<td>{esc(x["name"])}</td><td>{status_cell(x["pid"], tr)}</td></tr>'
        for x in procs
    )
    main = f"""      <div class="page-header">
        <div class="breadcrumb">
          <a href="{p}index.html">Home</a> &rsaquo;
          <a href="../index.html">{esc(l1_name)}</a>
        </div>
        <h1>{icon} {esc(l2_name)}</h1>
        <p>{done} of {len(procs)} processes complete</p>
      </div>
      <div class="card">
        <div class="card-header">Process List</div>
        <div class="card-body">
          <table class="l4-table" style="min-width:500px">
            <thead><tr><th>PID</th><th>L3 Process Name</th><th>Status</th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </div>
      </div>
"""
    return page_shell(esc(l2_name), f"{esc(l1_name)} &rsaquo; {esc(l2_name)}",
                      DEPTH_L2, main, active_pid=procs[0]["pid"] if procs else None)


def build_l1_index(l1_code, tr):
    icon, l1_name, l1_slug = L1_META[l1_code]
    groups = [g for g in TAXONOMY if g[0] == l1_code]
    all_procs = [p for p in PROCESSES if p["l1"] == l1_code]
    done = sum(1 for p in all_procs if is_complete(p["pid"], tr))
    fam = FAMILY[l1_code]
    p = prefix(DEPTH_L1)

    cards = []
    for _, l2_code, l2_name, l2_slug, names in groups:
        gp = group_processes(l1_code, l2_code)
        gdone = sum(1 for x in gp if is_complete(x["pid"], tr))
        cards.append(f"""    <div class="domain-card org-{fam}">
      <h3><a href="{l2_slug}/index.html">{esc(l2_name)}</a></h3>
      <p class="card-meta">{gdone}/{len(gp)} processes complete</p>
    </div>""")

    main = f"""      <div class="page-header">
        <div class="breadcrumb"><a href="{p}index.html">Home</a></div>
        <h1>{icon} {esc(l1_name)}</h1>
        <p>{done} of {len(all_procs)} processes complete across {len(groups)} process groups</p>
      </div>
      <div class="domain-grid">
{chr(10).join(cards)}
      </div>
"""
    return page_shell(esc(l1_name), esc(l1_name), DEPTH_L1, main,
                      active_pid=all_procs[0]["pid"] if all_procs else None)


def build_home(tr):
    done = sum(1 for p in PROCESSES if is_complete(p["pid"], tr))
    cards = []
    for l1_code, (icon, l1_name, l1_slug) in L1_META.items():
        procs = [p for p in PROCESSES if p["l1"] == l1_code]
        d = sum(1 for x in procs if is_complete(x["pid"], tr))
        fam = FAMILY[l1_code]
        cards.append(f"""    <div class="domain-card org-{fam}">
      <h3><a href="{l1_slug}/index.html">{icon} {esc(l1_name)}</a></h3>
      <p class="card-meta">
        <span class="nav-org-dot {fam}" style="display:inline-block;margin-right:4px"></span>
        {FAMILY_LABEL[fam]}
      </p>
      <p class="card-count">{d} / {len(procs)} processes complete</p>
    </div>""")
    cards.append(f"""    <div class="domain-card org-corp">
      <h3><a href="{EA_DIR_SLUG}/index.html">\U0001F5FA Enterprise Architecture</a></h3>
      <p class="card-meta"><span class="nav-org-dot corp" style="display:inline-block;margin-right:4px"></span>CORPORATE</p>
      <p class="card-count">{len(EA_DIAGRAMS)} EA diagrams</p>
    </div>""")

    main = f"""      <div class="page-header">
        <h1>{SITE_TITLE}</h1>
        <p>End-to-end business process reference for ocean container shipping and integrated
           logistics, modelled on A.P. Moller-Maersk &mdash; built for SAP consulting use cases.</p>
      </div>

      <div class="stats-bar">
        <div class="stat-card"><div class="stat-num">{done}</div><div class="stat-label">Processes Complete</div></div>
        <div class="stat-card"><div class="stat-num">{len(PROCESSES)}</div><div class="stat-label">Total Processes</div></div>
        <div class="stat-card"><div class="stat-num">{len(L1_META)}</div><div class="stat-label">L1 Domains</div></div>
        <div class="stat-card"><div class="stat-num">{len(TAXONOMY)}</div><div class="stat-label">L2 Process Groups</div></div>
        <div class="stat-card"><div class="stat-num accent">{len(EA_DIAGRAMS)}</div><div class="stat-label">EA Diagrams</div></div>
      </div>

      <div class="domain-grid">
{chr(10).join(cards)}
      </div>
"""
    return page_shell(SITE_TITLE, "Business Process Reference", DEPTH_ROOT, main)


def build_search_page():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Search &mdash; """ + SITE_TITLE + """</title>
  <link rel="stylesheet" href="assets/css/wiki.css">
</head>
<body>
  <div class="topbar">
    <button id="topbarToggle" aria-label="Menu"><span></span><span></span><span></span></button>
    <a class="topbar-brand" href="index.html">""" + SITE_TITLE + """</a>
    <span class="topbar-sub">Search Results</span>
    <span class="topbar-spacer"></span>
  </div>
  <div class="wiki-layout">
    <nav id="sidebar">
      <button id="sidebarToggle" title="Collapse sidebar">&#9664;</button>
""" + build_sidebar(DEPTH_ROOT) + """
    </nav>
    <main class="wiki-main">
      <div class="page-header">
        <h1>&#x1F50D; Search</h1>
        <p id="searchQueryDisplay"></p>
      </div>
      <div id="searchResults" class="card">
        <div class="card-body">
          <div class="search-count" id="resultCount">Loading&hellip;</div>
          <div id="resultList"></div>
        </div>
      </div>
    </main>
  </div>
  <div id="lightbox"><img id="lightboxImg" src="" alt=""></div>
  <script src="assets/js/wiki.js"></script>
  <script>
  (function(){
    var params = new URLSearchParams(window.location.search);
    var q = (params.get('q') || '').trim().toLowerCase();
    var qDisplay = document.getElementById('searchQueryDisplay');
    var countEl  = document.getElementById('resultCount');
    var listEl   = document.getElementById('resultList');
    if (!q) { countEl.textContent = 'Enter a search term.'; return; }
    qDisplay.textContent = 'Query: "' + params.get('q') + '"';

    fetch('search-index.json')
      .then(function(r){ return r.json(); })
      .then(function(idx){
        var tokens = q.split(/\\s+/).filter(Boolean);
        var results = idx.filter(function(item){
          var hay = (item.pid + ' ' + item.l1 + ' ' + item.l2 + ' ' +
                     item.l3 + ' ' + (item.systems||'')).toLowerCase();
          return tokens.every(function(t){ return hay.indexOf(t) >= 0; });
        });
        countEl.textContent = results.length + ' result' + (results.length !== 1 ? 's' : '') +
                              ' for "' + params.get('q') + '"';
        if (!results.length) {
          listEl.innerHTML = '<p class="text-muted mt-16">No processes matched your search.</p>';
          return;
        }
        listEl.innerHTML = results.map(function(r){
          return '<div class="search-result"><h4><a href="' + r.url + '">' +
                 r.pid + ' &mdash; ' + r.l3 + '</a></h4>' +
                 '<p>' + r.l1 + ' &rsaquo; ' + r.l2 + '</p></div>';
        }).join('');
      })
      .catch(function(){ countEl.textContent = 'Search index not yet available.'; });
  })();
  </script>
</body>
</html>
"""


def build_search_index(tr, extra=None):
    """Only completed processes go into the index. `extra` = {pid: systems_string}."""
    extra = extra or {}
    items = []
    for p in PROCESSES:
        if not is_complete(p["pid"], tr):
            continue
        items.append({
            "pid": p["pid"], "l1": p["l1_name"], "l2": p["l2_name"], "l3": p["name"],
            "url": p["path"], "systems": extra.get(p["pid"], ""),
        })
    for ea_id, ea_title, ea_desc in EA_DIAGRAMS:
        items.append({"pid": ea_id.upper(), "l1": "Enterprise Architecture",
                      "l2": "EA Diagrams", "l3": ea_title,
                      "url": f"{EA_DIR_SLUG}/{ea_id}/index.html", "systems": ea_desc})
    return json.dumps(items, ensure_ascii=False)

# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

PILOT_PIDS = ["VO-NP-01", "CM-TOS-01"]


def systems_map(tr):
    return {pid: rec.get("systems", "") for pid, rec in tr.items() if isinstance(rec, dict)}


def push_shell(tr):
    """Push everything that is not a process page: assets, home, indexes, search."""
    css_path = ROOT / "assets" / "css" / "wiki.css"
    js_path  = ROOT / "assets" / "js"  / "wiki.js"
    for f in (css_path, js_path):
        if not f.exists():
            sys.exit(f"Missing {f}. Copy wiki.css and wiki.js into assets/ before running.")

    log("pushing site shell …")
    gh_push_file(".nojekyll", "", "Add .nojekyll")
    gh_push_file("assets/css/wiki.css", css_path.read_text(encoding="utf-8"), "Update wiki.css")
    gh_push_file("assets/js/wiki.js",  js_path.read_text(encoding="utf-8"),  "Update wiki.js")
    gh_push_file("search.html", build_search_page(), "Update search page")
    rebuild_nav(tr, deploy=False)
    push_deploy()


def rebuild_nav(tr, deploy=True):
    """Regenerate and push home, every L1 index, every L2 index and the search index."""
    log("rebuilding navigation pages …")
    gh_push_file("index.html", build_home(tr), "Update home page")
    for l1_code, (_, _, l1_slug) in L1_META.items():
        gh_push_file(f"{l1_slug}/index.html", build_l1_index(l1_code, tr),
                     f"Update {l1_code} index")
        for g in [x for x in TAXONOMY if x[0] == l1_code]:
            gh_push_file(f"{l1_slug}/{g[3]}/index.html",
                         build_l2_index(l1_code, g[1], tr),
                         f"Update {l1_code}-{g[1]} index")
    gh_push_file("search-index.json", build_search_index(tr, systems_map(tr)),
                 "Update search index")
    if deploy:
        push_deploy()


def process_one(proc, tr):
    """Generate, render and push one process. Returns data dict on success."""
    log(f"── {proc['pid']} — {proc['name']}")

    data = generate_process_content(proc)
    if not data:
        log(f"{proc['pid']}: no usable content from Ollama — skipped", "ERROR")
        return None

    png = build_diagram(proc, data, kind="pid")
    if not png:
        log(f"{proc['pid']}: diagram failed after 3 attempts — skipped", "ERROR")
        return None

    if not gh_push_file(f"assets/img/{proc['slug']}.svg", png.read_bytes(),
                        f"Add {proc['pid']} BPMN diagram"):
        return None
    if not gh_push_file(proc["path"], build_process_page(proc, data),
                        f"Add {proc['pid']} {proc['name']}"):
        return None

    log(f"  pushed {proc['pid']}")
    return data


def flush_batch(pending, tr, verify=True):
    """Deploy, verify one page from the batch, then commit tracker + Excel rows."""
    if not pending:
        return
    push_deploy()
    ok = True
    if verify:
        last_proc, _ = pending[-1]
        url = f"{PAGES_BASE}/{last_proc['path']}"
        ok = verify_live(url)
        if ok:
            log(f"  verified live: {url}")
        else:
            log(f"  could not verify {url} — syncing tracker from the repo tree", "WARN")
            sync_tracker_from_github(tr)
    if ok:
        for proc, data in pending:
            url = f"{PAGES_BASE}/{proc['path']}"
            tr[proc["pid"]] = {
                "status": "Complete",
                "url": url,
                "completed_at": datetime.now().isoformat(timespec="seconds"),
                "systems": ", ".join(str(s) for s in data.get("systems", [])),
            }
            save_tracker(tr)
            excel_record(proc, data, url)
        log(f"  {len(pending)} process(es) recorded in tracker and Excel")
    pending.clear()


def select_targets(args, tr):
    if args.pid:
        pid = args.pid.upper()
        if pid not in BY_PID:
            sys.exit(f"Unknown PID {pid}")
        return [BY_PID[pid]]

    pool = PROCESSES
    if args.start:
        start = args.start.upper()
        if start not in BY_PID:
            sys.exit(f"Unknown PID {start}")
        idx = next(i for i, p in enumerate(PROCESSES) if p["pid"] == start)
        pool = PROCESSES[idx:]

    incomplete = pool if args.force else [p for p in pool if not is_complete(p["pid"], tr)]

    if args.count:
        return incomplete[: args.count]
    if args.full or args.start:
        return incomplete
    # pilot
    if args.force:
        return [BY_PID[pid] for pid in PILOT_PIDS]
    return [BY_PID[pid] for pid in PILOT_PIDS if not is_complete(pid, tr)]


def main():
    ap = argparse.ArgumentParser(description="Shipping Process Wiki generator")
    ap.add_argument("--full", action="store_true", help="all incomplete processes")
    ap.add_argument("--count", type=int, help="run exactly N incomplete processes")
    ap.add_argument("--start", help="resume from this PID")
    ap.add_argument("--pid", help="single process")
    ap.add_argument("--no-verify", action="store_true", help="skip the 90s live check")
    ap.add_argument("--force", action="store_true",
                    help="regenerate even if the tracker says Complete")
    ap.add_argument("--bootstrap", action="store_true",
                    help="push assets, home and indexes only, then exit")
    ap.add_argument("--rebuild-nav", action="store_true",
                    help="regenerate all index pages and the search index, no Ollama")
    ap.add_argument("--verify-every", type=int, default=10,
                    help="verify + record every N processes in a batch run (default 10)")
    args = ap.parse_args()

    for d in (DATA_DIR, DIAGRAM_DIR, IMG_DIR):
        d.mkdir(parents=True, exist_ok=True)

    tr = load_tracker()

    if args.bootstrap:
        push_shell(tr)
        log("bootstrap complete — now enable Pages: Settings → Pages → main → / (root)")
        return
    if args.rebuild_nav:
        rebuild_nav(tr)
        return

    targets = select_targets(args, tr)
    if not targets:
        log("nothing to do — everything selected is already complete")
        return

    is_pilot = not (args.full or args.count or args.start or args.pid)
    verify = not args.no_verify
    batch_size = 1 if is_pilot else max(1, args.verify_every)

    log(f"{len(targets)} process(es) queued | verify={'on' if verify else 'off'} | "
        f"record every {batch_size}")

    # first run against an empty repo needs the shell in place
    if not gh_get_sha("assets/css/wiki.css"):
        push_shell(tr)

    pending = []
    try:
        for i, proc in enumerate(targets, start=1):
            if is_complete(proc["pid"], tr) and not args.force:
                log(f"skip {proc['pid']} — already complete (use --force to rebuild)")
                continue
            data = process_one(proc, tr)
            if data:
                pending.append((proc, data))
            if len(pending) >= batch_size:
                flush_batch(pending, tr, verify)
            log(f"progress: {i}/{len(targets)}")
    except KeyboardInterrupt:
        log("interrupted — flushing what is done", "WARN")
        flush_batch(pending, tr, verify)
        rebuild_nav(tr)
        log("clean stop")
        return

    flush_batch(pending, tr, verify)
    rebuild_nav(tr)

    done = sum(1 for p in PROCESSES if is_complete(p["pid"], tr))
    log(f"run complete — {done}/{len(PROCESSES)} processes live at {PAGES_BASE}/")


if __name__ == "__main__":
    main()
