# Golden document: Maroc Telecom - Rapport financier annuel 2025

> **Golden v0, accepted 2026-10-29.** Read once from the PDF, not yet verified value by value. Items still marked UNCERTAIN stay flagged. When a parser in #10 disagrees with a value here, a person checks the page before counting it as a parser error, and this file is corrected if it is the one that's wrong. Pages 26 (no text layer) and 58 (loan table) are excluded until OCRed.
> Ticket: zzak00/bloomberg-invest#9 (ontology from #8). Prepared 2026-10-29 from the PDF only. No outside knowledge was used to fill values; anything not in the PDF is marked NOT FOUND or "not in document".
> Companion file: `figures.csv` (160 financial figure rows, golden v0).

## 1. Document

| Field | Value |
|---|---|
| Title | Rapport financier annuel 2025 (cover: "2025 Rapport financier annuel"; running footer: "Maroc Telecom • Rapport financier 2025") |
| Issuer | Maroc Telecom / Itissalat Al-Maghrib S.A (IAM) |
| Period | Fiscal year 1 Jan 2025 - 31 Dec 2025, with FY2024 and FY2023 comparatives (consolidated); FY2024 comparative only (company-only) |
| Pages | 90 |
| Language | French |
| Accounting bases | Consolidated IFRS as adopted by the EU (pp. 4, 23, 28); company-only Moroccan GAAP / CGNC ("référentiel comptable en vigueur au Maroc", p. 85) |
| Publication date | Not stated. Financial statements "arrêtés par le Conseil d'Administration le 12 février 2026" (p. 28); auditors' reports dated "Casablanca, le 12 février 2026" (pp. 77, 89) |
| Status note | p. 2: "Ce rapport n'est pas publié sous format ESEF et ne remplace pas la version officielle du rapport financier annuel qui sera incluse dans le document d'enregistrement universel." |
| Source URL | https://www.ammc.ma/sites/default/files/Maroc_Telecom_RFA_2025.pdf |
| Local file | `source/Maroc_Telecom_RFA_2025.pdf` (4 696 762 bytes, PDF 1.7) |
| SHA256 | `90e8b73c7f11bfde45d0c7ddb3ce506d162bac2030244d48d9ca2f641ddd4214` |

## 2. Section outline

The printed Sommaire (p. 2) lists only 4 top-level sections; the tree below is reconstructed from the headings on the pages.

- Cover (p. 1), Sommaire (p. 2)
- **1. RÉSULTATS CONSOLIDÉS DES TROIS DERNIERS EXERCICES** (pp. 3-5; p. 3 is an image divider)
  - 1.1 Chiffres consolidés en dirham (p. 4)
  - 1.2 Chiffres consolidés en euro (pp. 4-5)
- **2. VUE D'ENSEMBLE** (pp. 6-21; p. 6 divider)
  - 2.1 Périmètre de consolidation (pp. 7-8)
  - 2.2 Résultats comparés par zone géographique (pp. 9-20)
    - 2.2.1 Comparaison des données 2024 et 2025 (pp. 9-14): 2.2.1.1 Résultats consolidés du Groupe (pp. 9-10); 2.2.1.2 Activités au Maroc (p. 11); 2.2.1.3 Filiales Moov Africa (pp. 12-13); Notes (1)-(11) (p. 14)
    - Annexe 1 : Passage des indicateurs financiers ajustés aux indicateurs financiers publiés; Annexe 2 : Impact de la norme IFRS 16 (p. 15)
    - 2.2.2 Comparaison des données 2023 et 2024 (pp. 15-20): 2.2.2.1 Groupe (pp. 15-16); 2.2.2.2 Activités au Maroc (pp. 17-18); 2.2.2.3 Activités à l'International (pp. 19-20)
  - 2.3 Passage des comptes sociaux aux comptes consolidés (p. 21)
- **3. COMPTES CONSOLIDÉS DU GROUPE MAROC TELECOM AU 31 DÉCEMBRE 2023, 2024 ET 2025** (pp. 22-77; p. 22 divider)
  - Primary statements: situation financière (p. 23), résultat global (p. 24), flux de trésorerie (p. 25), variation des capitaux propres (p. 26), capital / shareholders (p. 27)
  - Notes 1-34 (pp. 28-72): N1 Principes comptables (pp. 28-39); N2 Périmètre (pp. 40-41); N3 Goodwill (pp. 41-43); N4 Autres immobilisations incorporelles (pp. 44-45); N5 Immobilisations corporelles (pp. 45-47); N6 Titres mis en équivalence (p. 47); N7 Actifs financiers non courants (pp. 47-49); N8 Impôts différés (p. 50); N9 Stocks, N10 Créances (pp. 51-52); N11 Actifs financiers à court terme (p. 52); N12 Trésorerie (p. 53); N13 Dividendes, N14 Provisions (pp. 54-55); N15 Emprunts (pp. 56-58); N16-N18 (p. 59); N19-N21 (p. 60); N22-N23 (p. 61); N24-N25 (pp. 62-63); N26 (p. 63); N27-N28 (pp. 64-65); N29-N30 Parties liées (pp. 66-67); N31 Engagements (pp. 67-68); N32 Gestion des risques (pp. 68-70); N33 Événements post clôture (p. 70); N34 IFRS 16 (pp. 71-72)
  - Rapport des commissaires aux comptes (consolidated) (pp. 73-77)
- **4. COMPTES SOCIAUX DE MAROC TELECOM** (pp. 78-89; p. 78 divider)
  - Bilan actif (p. 79), Bilan passif (p. 80), Compte de produits et charges (p. 81)
  - Commentary: principaux indicateurs, compte de produits et charges, comptes de bilan (pp. 82-84)
  - Rapport général des commissaires aux comptes (company) (pp. 85-89)
- Back cover with legal identity (p. 90)

## 3. Entities

ISIN/ticker: **no ISIN or ticker appears anywhere in the document** (searched all 90 pages). First page = first page where the entity is named in text.

| # | Canonical name | Kind | Aliases as written | ISIN / ticker | First page |
|---|---|---|---|---|---|
| E1 | Maroc Telecom | company | Maroc Telecom; Maroc Télécom; Groupe Maroc Telecom; Maroc Telecom SA; Itissalat Al-Maghrib; ITISSALAT AL-MAGHRIB SA; Itissalat Al-Maghrib (IAM) S.A; IAM; Groupe MT | not in document (listed, see L1-L2) | 2 |
| E2 | Etisalat | company | Etisalat; Emirates Telecommunications Corporation; Groupe Etisalat | not in document | 27 |
| E3 | Royaume du Maroc | state | Royaume du Maroc; Etat Marocain; l'Etat (p. 32) | n/a | 27 |
| E4 | Société de Participation dans les Télécommunications | holding | Société de Participation dans les Télécommunications (SPT) | n/a | 54 |
| E5 | Free float | aggregate | "Autres" (p. 27, p. 54) - mapped to the free float aggregate (decided 2026-10-29), see SH3 | n/a | 27 |
| E6 | Treasury shares | aggregate | "actions propres" (pp. 26, 35) | n/a | 26 |
| E7 | Etat Malien | state | l'Etat Malien | n/a | 7 |
| E8 | Compagnie Mauritanienne de Communication | holding | Compagnie Mauritanienne de Communications « CMC » (p. 7); Compagnie Mauritanienne de Communication (CMC) (p. 40); CMC | n/a | 7 |
| E9 | Mauritel | company | Mauritel; Mauritel SA (Fixe); Mauritel Mobile (merged); Moov Mauritel | not in document | 7 |
| E10 | Onatel | company | Onatel; l'Onatel; Moov Africa Onatel | listed, code not in document (L3) | 7 |
| E11 | Gabon Telecom | company | Gabon Telecom; Moov Africa Gabon Telecom | n/a | 7 |
| E12 | Sotelma | company | Sotelma; la Sotelma; Moov Africa Sotelma; Moov Africa Mali | n/a | 7 |
| E13 | Casanet | company | Casanet | n/a | 7 |
| E14 | Moov Africa Côte d'Ivoire | company | Moov Africa Côte d'Ivoire; Moov Africa CIV; Moov Africa CDI | n/a | 7 |
| E15 | Moov Africa Bénin | company | Moov Africa Bénin; Moov Africa Benin | n/a | 7 |
| E16 | Moov Africa Togo | company | Moov Africa Togo | n/a | 7 |
| E17 | Moov Africa Niger | company | Moov Africa Niger; "Moov Afrivca Niger" (typo, p. 44) | n/a | 8 |
| E18 | Moov Africa Centrafrique | company | Moov Africa Centrafrique | n/a | 8 |
| E19 | Moov Africa Tchad | company | Moov Africa Tchad | n/a | 8 |
| E20 | MT CASH | company | MT CASH; MT Cash | n/a | 8 |
| E21 | Uni Fiber | company | Uni Fiber; UNI FIBER; Unifiber S.A | n/a | 8 |
| E22 | Uni Tower | company | Uni Tower; UNI TOWER; Unitower S.A | n/a | 8 |
| E23 | Wana Corporate | company | WANA (p. 8); Wana; Wana Corporate; WANA Corporate; WANA CORPORATE; INWI (p. 62, brand of Wana Corporate; alias decided 2026-10-29) | not in document | 8 |
| E24 | Atlantique Telecom Gabon | company | Atlantique Telecom Gabon (absorbed by Gabon Telecom 29 June 2016) | n/a | 7 |
| E25 | ANRT | state | ANRT (regulator) | n/a | 8 |
| E26 | MT Fly | company | MT Fly | n/a | 8 |
| E27 | Moov Money Tchad | company | Moov Money Tchad; (group label "Moov Money", pp. 8, 48) | n/a | 48 |
| E28 | Moov Money Flooz | company | Moov Money Flooz | n/a | 48 |
| E29 | Moov Money Mali | company | Moov Money Mali | n/a | 48 |
| E30 | Moov Money Gabon Telecom | company | Moov Money Gabon Telecom | n/a | 48 |
| E31 | RASCOM | company | RASCOM | n/a | 8 |
| E32 | Autoroutes du Maroc | company | Autoroutes du Maroc; Autoroute du Maroc | n/a | 8 |
| E33 | Arabsat | company | Arabsat | n/a | 8 |
| E34 | Thuraya | company | Thuraya | n/a | 48 |
| E35 | Sonatel | company | Sonatel | n/a | 48 |
| E36 | CMTL | company | CMTL | n/a | 48 |
| E37 | INMARSAT | company | INMARSAT | n/a | 48 |
| E38 | IMT/GIE | company | IMT/GIE | n/a | 48 |
| E39 | Hôtels de la Gare | company | Hôtels de la Gare | n/a | 48 |
| E40 | Incubateur numérique Gabon | company | Incubateur numérique Gabon | n/a | 48 |
| E41 | Rothschild Martin Maurel | bank | Rothschild Martin Maurel | n/a | 52 |
| E42 | Société Financière Internationale | bank | Société Financière Internationale (IFC); IFC | n/a | 56 |
| E43 | EDCH | company | EDCH | n/a | 66 |
| E44 | Etihad Etisalat Company | company | Etihad Etisalat Company (Mobily); Mobily | n/a | 66 |
| E45 | Ericsson | company | Ericsson | n/a | 67 |
| E46 | Bank Al-Maghrib | bank | Bank-Al Maghrib | n/a | 69 |
| E47 | ONPT | state | ONPT (pre-1998 public operator) | n/a | 32 |
| E48 | Bourse de Casablanca | company (exchange; no exchange kind in ontology) | bourse de Casablanca | n/a | 52 |
| E49 | Bourse de Paris | company (exchange; no exchange kind in ontology) | bourse de Paris | n/a | 52 |
| E50 | Deloitte Audit | audit firm | Deloitte Audit | n/a | 77 |
| E51 | BDO SA | audit firm | BDO SA | n/a | 77 |
| P1 | Lamia LEMKECHER | person | Madame Lamia LEMKECHER | n/a | 10 |
| P2 | Luis ENRIQUEZ | person | Monsieur Luis ENRIQUEZ | n/a | 10 |
| P3 | Adnane FAOUZI | person | Adnane FAOUZI (Associé, Deloitte Audit) | n/a | 77 |
| P4 | Abderrahim GRINE | person | Abderrahim GRINE (Associé, BDO SA) | n/a | 77 |

Total: 55 entities (51 organisations, 4 persons). Deliberately excluded: standard setters and data sources (IASB, IFRS IC, CNCC, ANC, FMI, Dataxis), and the ~20 lending banks named in the p. 58 loan table (no reliable text layer, see Hard cases).

## 4. Facts by kind

### 4.1 Shareholding (36)

| # | Holder | Held | % | Shares | As of | Citation |
|---|---|---|---|---|---|---|
| SH1 | Etisalat | Maroc Telecom | 53% | not stated (total shares 879 095 340) | 2025-12-31 | p. 27, text: "- Etisalat : 53% ;" |
| SH2 | Royaume du Maroc | Maroc Telecom | 22% | not stated | 2025-12-31 | p. 27, text: "- Royaume du Maroc : 22% ;" |
| SH3 | Free float (written "Autres"; decided 2026-10-29: free float aggregate, may include treasury shares) | Maroc Telecom | 25% | not stated | 2025-12-31 | p. 27, text: "- Autres : 25% ;" |
| SH4 | Société de Participation dans les Télécommunications (SPT) | Maroc Telecom | not stated (receives 666 of 1 257 MAD m dividends, about 53%. Decided 2026-10-29: no SPT -> Etisalat link in the golden set, because this report does not state it) | not stated | FY2025 | p. 54, table "NOTE 13. DIVIDENDES", row "-Société de Participation dans les Télécommunications (SPT)", col 31-déc.-25 |
| SH5 | Maroc Telecom | CMC | 80% interest / 80% control | not stated | 2025-12-31 | p. 40, table "NOTE 2. PÉRIMÈTRE DE CONSOLIDATION", row CMC 31-déc-25 |
| SH6 | Maroc Telecom (via CMC) | Mauritel | 41,2% interest; 51,5% voting rights | not stated | 2025-12-31 (acquired 12 April 2001) | p. 7, text: "Maroc Telecom détient 41,2% des parts d'intérêt dans l'opérateur historique mauritanien" |
| SH7 | Maroc Telecom | Onatel | 61% | not stated | 2025-12-31 (61% since 17 April 2018) | p. 40 row Onatel; p. 7 text |
| SH8 | Maroc Telecom | Gabon Telecom | 51% | not stated | 2025-12-31 | p. 40 row Gabon Telecom |
| SH9 | Maroc Telecom | Sotelma | 44% (was 51% at 2024-12-31) | not stated | 2025-12-31 (change at 30 June 2025) | p. 40 row Sotelma*; p. 7 text: "Maroc Telecom a cédé 7% du capital à l'Etat Malien portant sa participation à 44%" |
| SH10 | Etat Malien | Sotelma | acquired 7% (total holding not stated) | not stated | 2025-06-30 | p. 7, same span as SH9 |
| SH11 | Maroc Telecom | Casanet | 100% | not stated | 2025-12-31 | p. 40 row Casanet |
| SH12 | Maroc Telecom | Moov Africa Côte d'Ivoire | 85% | not stated | 2025-12-31 | p. 40 row Moov Africa Côte d'Ivoire |
| SH13 | Maroc Telecom | Moov Africa Bénin | 100% | not stated | 2025-12-31 | p. 40 |
| SH14 | Maroc Telecom | Moov Africa Togo | 95% | not stated | 2025-12-31 | p. 40 |
| SH15 | Maroc Telecom | Moov Africa Niger | 100% | not stated | 2025-12-31 | p. 40 |
| SH16 | Maroc Telecom | Moov Africa Centrafrique | 100% | not stated | 2025-12-31 | p. 40 |
| SH17 | Maroc Telecom | Moov Africa Tchad | 100% | not stated | 2025-12-31 | p. 40 |
| SH18 | Maroc Telecom | MT CASH | 100% | not stated | 2025-12-31 | p. 40 row MT CASH **; p. 8 text |
| SH19 | Maroc Telecom | Uni Tower | 50% | not stated | 2025-12-31 | p. 40 row UNI TOWER***; p. 8 text "détenue à hauteur de 50%" |
| SH20 | Maroc Telecom | Uni Fiber | 50% | not stated | 2025-12-31 | p. 40 row UNI FIBER*** |
| SH21 | Wana Corporate | Uni Fiber, Uni Tower | not stated (co-venturer) | not stated | FY2025 | p. 47, text: "Les joint-ventures « Uni Fiber » et « Uni Tower », créées avec Wana Corporate" |
| SH22 | Maroc Telecom group | RASCOM | 9% | not stated | 2025-12-31 | p. 48, table "7.1 Titres de participations non consolidés - Exercice 2025", col "Pourcentage détenu" |
| SH23 | Maroc Telecom group | CMTL | 25% | not stated | 2025-12-31 | p. 48, same table |
| SH24 | Maroc Telecom group | IMT/GIE | 20% | not stated | 2025-12-31 | p. 48 |
| SH25 | Maroc Telecom group | MT Fly | 100% | not stated | 2025-12-31 | p. 48 |
| SH26 | Maroc Telecom group | Incubateur numérique Gabon | 5% | not stated | 2025-12-31 | p. 48 |
| SH27 | Maroc Telecom group | Moov Money Tchad | 100% | not stated | 2025-12-31 | p. 48 |
| SH28 | Maroc Telecom group | Moov Money Flooz | 100% | not stated | 2025-12-31 | p. 48 |
| SH29 | Maroc Telecom group | Moov Money Mali | 100% | not stated | 2025-12-31 | p. 48 |
| SH30 | Maroc Telecom group | Moov Money Gabon Telecom | 100% | not stated | 2025-12-31 | p. 48 |
| SH31 | Maroc Telecom group | Arabsat | "NS" (not significant, no %) | not stated | 2025-12-31 | p. 48 |
| SH32 | Maroc Telecom group | Autoroutes du Maroc | "NS" | not stated | 2025-12-31 | p. 48 |
| SH33 | Maroc Telecom group | Thuraya | "NS" | not stated | 2025-12-31 | p. 48 |
| SH34 | Maroc Telecom group | Sonatel | "NS" | not stated | 2025-12-31 | p. 48 |
| SH35 | Maroc Telecom group | INMARSAT | "NS" | not stated | 2025-12-31 | p. 48 |
| SH36 | Maroc Telecom group | Hôtels de la Gare | "NS" | not stated | 2025-12-31 | p. 48 |

"Maroc Telecom group" in SH22-SH36: the table does not say which group entity holds each stake (UNCERTAIN; Moov Money entities are probably held through the subsidiaries).

### 4.2 Board seat (3)

| # | Person / org | Company | Role | Representative | Citation |
|---|---|---|---|---|---|
| BS1 | Lamia LEMKECHER | Maroc Telecom | Member, Conseil d'Administration (co-opted 5 Dec 2025; term to the AGO on FY2030 accounts) | n/a | p. 10, text: "a procédé à la cooptation de Madame Lamia LEMKECHER en qualité de membre du Conseil d'Administration et du Comité d'Audit" |
| BS2 | Lamia LEMKECHER | Maroc Telecom | Member, Comité d'Audit | n/a | p. 10, same span |
| BS3 | Luis ENRIQUEZ | Maroc Telecom | Former member, Conseil d'Administration and Comité d'Audit (replaced 5 Dec 2025) | n/a | p. 10, text: "en remplacement de Monsieur Luis ENRIQUEZ" |

No other directors, chairman or CEO are named in the document.

### 4.3 Audit mandate (4)

| # | Firm | Company | Scope | Fiscal years | Signing partner | Citation |
|---|---|---|---|---|---|---|
| AM1 | Deloitte Audit | Itissalat Al-Maghrib (IAM) S.A and subsidiaries | consolidated IFRS | FY2025 (mandate term not stated) | Adnane FAOUZI, Associé | p. 77, signature block "LES COMMISSAIRES AUX COMPTES" |
| AM2 | BDO SA | same | consolidated IFRS | FY2025 | Abderrahim GRINE, Associé | p. 77 |
| AM3 | Deloitte Audit | Itissalat Al-Maghrib S.A | company-only | FY2025 | Adnane FAOUZI | p. 89 |
| AM4 | BDO SA | Itissalat Al-Maghrib S.A | company-only | FY2025 | Abderrahim GRINE | p. 89 |

### 4.4 Listing (3)

| # | Company | Exchange | Ticker | ISIN | Compartment | Sector | Listing date | Citation |
|---|---|---|---|---|---|---|---|---|
| L1 | Maroc Telecom | Bourse de Casablanca | NOT FOUND | NOT FOUND | NOT FOUND | NOT FOUND | NOT FOUND | p. 52, text: "d'un contrat de régulation de cours à la bourse de Casablanca pour assurer la liquidité du titre Maroc Telecom" |
| L2 | Maroc Telecom | Bourse de Paris | NOT FOUND | NOT FOUND | NOT FOUND | NOT FOUND | NOT FOUND | p. 52, text: "la mise en œuvre d'un contrat de liquidité à la bourse de Paris" |
| L3 | Onatel | not named | NOT FOUND | NOT FOUND | NOT FOUND | NOT FOUND | NOT FOUND | p. 41, text: "l'Onatel, l'unique filiale cotée en bourse du Groupe" |

### 4.5 Consolidation (15)

Source table: p. 40 "NOTE 2. PÉRIMÈTRE DE CONSOLIDATION DE MAROC TELECOM" (columns: Forme juridique, % d'intérêt, % de contrôle, Méthode de consolidation; IG = intégration globale = full, ME = mise en équivalence = equity). Parent for all: Maroc Telecom.

| # | Subsidiary | Method | % control 2025 | % interest 2025 | 2024 comparative | Since | Citation |
|---|---|---|---|---|---|---|---|
| CO1 | CMC | full | 80% | 80% | 80% / 80% IG | n/a | p. 40 row CMC 31-déc-25 |
| CO2 | Mauritel | full | 51,5% (voting rights) | 41,2% | not stated | 1 July 2004 | p. 7, text: "Maroc Telecom consolide Mauritel par intégration globale depuis le 1er juillet 2004" (Mauritel itself is not a row in Note 2) |
| CO3 | Onatel | full | 61% | 61% | 61% / 61% IG | 1 Jan 2007 | p. 40 row Onatel |
| CO4 | Gabon Telecom | full | 51% | 51% | 51% / 51% IG | 1 March 2007 | p. 40 row Gabon Telecom |
| CO5 | Sotelma | full | 44% | 44% | 51% / 51% IG | 1 Aug 2009 | p. 40 row Sotelma*; footnote * p. 41: control kept through shareholders' pact |
| CO6 | Casanet | full | 100% | 100% | 100% / 100% IG | 1 Jan 2011 | p. 40 row Casanet |
| CO7 | Moov Africa Côte d'Ivoire | full | 85% | 85% | 85% / 85% IG | 31 Jan 2015 | p. 40 |
| CO8 | Moov Africa Bénin | full | 100% | 100% | 100% / 100% IG | 31 Jan 2015 | p. 40 |
| CO9 | Moov Africa Togo | full | 95% | 95% | 95% / 95% IG | 31 Jan 2015 | p. 40 |
| CO10 | Moov Africa Niger | full | 100% | 100% | 100% / 100% IG | 31 Jan 2015 | p. 40 |
| CO11 | Moov Africa Centrafrique | full | 100% | 100% | 100% / 100% IG | 31 Jan 2015 | p. 40 |
| CO12 | Moov Africa Tchad | full | 100% | 100% | 100% / 100% IG | 1 July 2019 | p. 40 |
| CO13 | MT CASH | full | 100% | 100% | table shows 100% / 100% IG for 2024 and 2023 (contradicts p. 41 footnote ** and p. 48: consolidated only from Q4 2025) | Q4 2025 | p. 40 row MT CASH **; p. 41 footnote ** |
| CO14 | Uni Tower | equity | 50% | 50% | "ME" with blank % (did not exist) | Q4 2025 | p. 40 row UNI TOWER***; p. 41 footnote *** |
| CO15 | Uni Fiber | equity | 50% | 50% | "ME" with blank % | Q4 2025 | p. 40 row UNI FIBER*** |

### 4.6 Dividend (3)

| # | Company | Per share | Fiscal year | Total | Payment date | Citation |
|---|---|---|---|---|---|---|
| D1 | Maroc Telecom | 4,00 MAD (proposed to the next AGM) | FY2025 | "3,5 milliards de dirhams" | NOT FOUND | p. 10, text: "la distribution d'un dividende de 4,00 dirhams par action, représentant un montant global de 3,5 milliards de dirhams" |
| D2 | Maroc Telecom | 1,43 MAD | FY2024 | "1,26 milliard de dirhams" | NOT FOUND | p. 16, text: "la distribution d'un dividende de 1,43 dirham par action" |
| D3 | Maroc Telecom | (paid in 2025, consistent with D2: 1,43 x 879 095 340 = 1 257 MAD m) | FY2024 paid during FY2025 | 1 257 MAD m: Etat Marocain 277, SPT 666, Autres 314 | NOT FOUND (only year) | p. 54, table "NOTE 13. DIVIDENDES", rows "-Etat Marocain", "-Société de Participation...", "-Autres", "Total (b)", col 31-déc.-25 |

### 4.7 Auditor opinion (2)

| # | Scope | Opinion | Quoted reason | Citation |
|---|---|---|---|---|
| AO1 | Consolidated IFRS FY2025 | Unqualified with emphasis of matter ("Observation") | "Nous vous renvoyons aux mentions insérées dans les notes 31.4 et 2 qui exposent les impacts de la clôture des litiges relatifs au dégroupage et de l'évolution de la participation de Maroc Telecom dans le capital de Sotelma. Notre conclusion n'est pas modifiée à cet égard." | p. 73, sections "Opinion" and "Observation" |
| AO2 | Company-only CGNC FY2025 | Unqualified with emphasis of matter ("Observation") | "Nous vous renvoyons aux mentions insérées dans les états B15 et B3 qui exposent les impacts de la clôture des litiges relatifs au dégroupage et de la cession partielle de la participation de Maroc Telecom dans le capital de Sotelma." | p. 85 |

Key audit matters: consolidated = revenue recognition, goodwill valuation, provisions (pp. 74-75); company = revenue recognition, valuation of titres de participation, provisions (pp. 86-87).

### 4.8 Related-party agreement (11)

Amounts in MAD millions. Source for RP1-RP8: p. 67, tables "Exercice 2025" / "Exercice 2024" under "30.4. Autres parties liées" (heading on p. 66), columns Etisalat / EDCH / Mobily / Autres, rows Chiffre d'affaires / Charges / Créances / Dettes.

| # | Parties | Covers | Amounts | Year | Citation |
|---|---|---|---|---|---|
| RP1 | Maroc Telecom - Etisalat | transactions under strategic cooperation with Groupe Etisalat | revenue 275; charges 41; receivables 95; payables 22 | 2025 | p. 67, col Etisalat, Exercice 2025 |
| RP2 | Maroc Telecom - EDCH | same | revenue 68; charges 32; receivables 26; payables 5 | 2025 | p. 67, col EDCH |
| RP3 | Maroc Telecom - Etihad Etisalat Company (Mobily) | same | revenue 34; charges 5; receivables 17; payables 7 | 2025 | p. 67, col Mobily |
| RP4 | Maroc Telecom - other Etisalat sister companies ("Autres") | same | revenue 2; charges 1; receivables -1; payables -1 | 2025 | p. 67, col Autres |
| RP5 | Maroc Telecom - Etisalat | same | revenue 192; charges 56; receivables 65; payables 13 | 2024 | p. 67, Exercice 2024 |
| RP6 | Maroc Telecom - EDCH | same | revenue 29; charges 4; receivables 65; payables 26 | 2024 | p. 67 |
| RP7 | Maroc Telecom - Mobily | same | revenue 20; charges 10; receivables 5; payables 3 | 2024 | p. 67 |
| RP8 | Maroc Telecom - Autres | same | revenue 7; charges 11; receivables 4; payables 2 | 2024 | p. 67 |
| RP9 | Maroc Telecom - mandataires sociaux, dirigeants, administrateurs | remuneration | total 177 (short-term 58; termination indemnities 119); 2024: 214 | 2025 | p. 66, table "30.2. Rémunérations des mandataires sociaux...", row Total |
| RP10 | Maroc Telecom - Uni Fiber, Uni Tower (JVs with Wana Corporate) | joint ventures, equity-accounted; amounts "non significatives" | equity-accounted investment 549 (balance sheet line "Titres mis en équivalence", p. 23); share of result -1 (p. 61) | 2025 | p. 66, "30.3. Sociétés mises en équivalence"; p. 47 Note 6 |
| RP11 | Itissalat Al-Maghrib S.A - Unitower S.A, Unifiber S.A | statutory disclosure (art. 172 loi 17-95) of new shareholdings | not stated | 2025 | p. 89, text: "a procédé au cours de l'exercice à la prise de participation dans les sociétés Unitower S.A et Unifiber S.A créés en 2025" |

The auditors' special report on regulated agreements (conventions réglementées) is not part of this document.

### 4.9 Financial figure

160 rows in `figures.csv` (117 consolidated IFRS, 43 company-only CGNC). Coverage of required line items:

| Line item | Consolidated IFRS FY2025 / FY2024 (MAD m) | Company-only CGNC FY2025 / FY2024 (MAD thousands unless noted) |
|---|---|---|
| revenue | 36 681 / 36 699 (p. 24) | 18 131 524 / 18 390 609 (p. 81) |
| gross profit | **NOT FOUND**: P&L by nature (Note 1 §3.1 p. 28); looked at pp. 4, 24, 59 (Note 18), 81. No marge brute line | **NOT FOUND**: état des soldes de gestion not included (p. 85 lists it as audited but it is not reproduced) |
| EBITDA | 18 493 / 19 188 (p. 9, non-GAAP) ; EBIT + D&A route does not reconcile, see notes in CSV | **NOT FOUND** (EBE is in the ESG, not reproduced); D&A 2 891 883 / 2 918 943 (p. 81) |
| operating income (EBIT) | 13 547 / 6 062 (p. 24) | 6 539 241 / 7 268 276 (p. 81) |
| net income | 7 923 / 2 660 (p. 24) | 5 805 375 / 1 592 703 (p. 81) |
| net income group share | 6 968 / 1 801 (p. 24) | n/a |
| interest expense | gross -1 053 / -1 074 (p. 24); borrowings -955 / -976, leases -98 / -98 (p. 62) | 308 603 / 390 319 (p. 81) |
| interest income | 65 / 59 (p. 24) | 74 810 / 23 963 (p. 81, includes other financial income) |
| total assets | 75 811 / 70 374 (p. 23) | 40 499 963 / 39 905 156 (p. 79) |
| current assets | 15 168 / 15 089 (p. 23) | 8 113 503 / 8 047 983 (p. 79, excl. trésorerie) |
| current liabilities | 39 054 / 45 266 (p. 23) | 14 509 351 / 11 006 190 (p. 80, excl. trésorerie-passif) |
| cash and equivalents | 1 966 / 1 979 (p. 23) | 341 255 / 270 518 (p. 79) |
| interest-bearing debt short term | 9 154 / 18 812 (p. 23); split p. 56 | bank overdrafts 1 724 996 / 12 155 557 (p. 80) |
| interest-bearing debt long term / long-term debt | 10 449 / 5 630 (p. 23); split p. 56 | 3 001 494 / 1 494 (p. 80) |
| equity | 24 785 / 18 702 | 21 247 673 / 16 699 288 (p. 80) |
| equity group share | 20 478 / 14 908 | n/a |
| minority interests | 4 307 / 3 794 | n/a |
| receivables | 12 554 / 12 698 (p. 23); trade 9 393 / 8 981 (p. 51) | trade 6 927 368 / 6 543 082 (p. 79) |
| shares outstanding | 879 095 340 / 879 095 340 (pp. 24, 27, 64) | capital 5 274 572 (thousands MAD); par value derivable 6 MAD (5 274 572 040 / 879 095 340), not stated |
| treasury shares | **NOT FOUND** as a count; only equity movement "Opérations sur actions propres" 30 / -35 MAD m (p. 26, image, UNCERTAIN); looked at pp. 23, 24, 26, 27, 35, 52, 64 | **NOT FOUND** |
| dividend per share | 4,00 MAD (FY2025, proposed, p. 10) / 1,43 MAD (FY2024, p. 16) | same company |
| operating cash flow | 18 499 / 11 598 (p. 25); CFFO 8 022 / 9 101 (p. 9) | **NOT FOUND** (tableau de financement not reproduced) |
| capex | accrual 10 894 / 11 164 (p. 9); cash -9 404 / -11 663 (p. 25) | "Investissements" 5 307 / 3 130 MAD m (p. 82) |
| dividends paid | -1 257 / -3 691 to shareholders; -746 / -831 to minorities (p. 25) | "1,3 milliards" (p. 84 text, UNCERTAIN) |
| tax rate / tax expense | tax -4 610 / -2 291 (p. 24); effective 37% / 46% (p. 62); statutory 34% / 33% (p. 63) | IS 2 400 505 / 276 712 (p. 81); rate **NOT FOUND** (35,0% deferred-tax rate for Maroc Telecom is in consolidated Note 25, p. 63) |

## 5. Multi-page tables

| Table | Pages | Kind of split |
|---|---|---|
| Consolidated "Questions clés identifiées / Notre réponse" (key audit matters) | 74-75 | true split: the goodwill row continues across the page break |
| Company "Questions clés identifiées / Notre réponse" | 86-87 | true split: the "Evaluation des titres de participation" row continues across the page break |
| Bilan comptes sociaux (Actif p. 79, Passif p. 80) | 79-80 | one logical balance sheet, two physical tables with different column sets |
| Note 4 movement tables (Exercice 2025, 2024 / Exercice 2023) | 44-45 | one note, per-year sub-tables across pages |
| Note 5 movement tables (2025, 2024 / 2023) | 46-47 | same |
| Note 7.1 Titres de participations non consolidés (2025, 2024 / 2023) | 48-49 | same |
| Note 15.2 Ventilation par échéance (2025 / 2024, 2023) | 56-57 | same |
| Note 28.2 Ventilation du bilan par zone géographique (2025 / 2024, 2023) | 64-65 | same |
| Note 30.4 Autres parties liées (intro on p. 66, tables on p. 67) | 66-67 | caption and tables separated by the page break |
| Note 2 Périmètre (table p. 40, footnotes *, **, *** on p. 41) | 40-41 | footnotes resolved on the next page |

## 6. Cross-references (15 examples)

| # | Source (page, text) | Target | Target page |
|---|---|---|---|
| X1 | p. 7, "voir tableau de variation des capitaux propres" | Tableau de variation des capitaux propres consolidés | 26 |
| X2 | p. 9, "Les ajustements des indicateurs financiers sont détaillés dans l'annexe 1" | Annexe 1 | 15 |
| X3 | p. 9, superscripts "(1)", "(2)", "(3)" on table cells | Notes (1)-(11) | 14 |
| X4 | p. 23, Note column "15" on "Emprunts et autres passifs financiers à long terme" | Note 15 | 56 |
| X5 | p. 25, Note column "13" on "Dividendes versés aux actionnaires" | Note 13 | 54 |
| X6 | p. 29, "(cf. note 14)" | Note 14 Provisions | 54 |
| X7 | p. 29, "(cf. note 3)" | Note 3 Goodwill | 41 |
| X8 | p. 29, "(cf. note 8)" | Note 8 Impôts différés | 50 |
| X9 | p. 29, "la note 2 « Périmètre de consolidation »" | Note 2 | 40 |
| X10 | p. 41, footnote *, "voir tableau de variation des capitaux propres" | Tableau de variation des capitaux propres | 26 |
| X11 | p. 47, Note column "7.1" | 7.1 Titres de participations non consolidés | 48 |
| X12 | p. 73, "les notes 31.4 et 2" | **31.4 does not exist** (closest: 31.3 Actifs et passifs éventuels, p. 68); Note 2 p. 40 | 68 (UNCERTAIN), 40 |
| X13 | p. 74, "détaillées dans la note 3.15" | Note 1, §3.15 Chiffre d'affaires | 38 |
| X14 | p. 75, "Comme indiqué dans la note 3.11" | Note 1, §3.11 Provisions | 37 |
| X15 | p. 85, "les états B15 et B3"; p. 86 "l'état A1 des ETIC"; p. 87 "état A1-9" | ETIC statements: **not in this document** (dangling) | n/a |

## 7. Hard cases for the parser

1. **Pages without a usable text layer.** p. 26 (Tableau de variation des capitaux propres): only the two footnotes extract as text; the whole table is a graphic. p. 58 (15.3 Tableau d'analyse, about 150 loan rows by subsidiary, lender, currency, maturity, 3 year columns): no text, very small type, unreadable at normal render resolution, needs OCR at high DPI. Cover p. 1 has no text at all; divider pages 3, 6, 22, 78 are full-page photos with a small heading text layer.
2. **Mixed scales.** Consolidated in "millions MAD"; p. 5 in "millions EUR"; company-only pp. 79-81 in "millier de MAD"; pp. 82-84 back to "millions de dirhams"; text uses "milliards" ("3,5 milliards", "6,368 milliards") and "MMAD" ("700MMAD", "–3 743 MMAD"); operating KPIs use "(000)" = thousands of customers (not money); ARPU in "MAD/mois"; ratios "1,1x"; margins "pt".
3. **Negative numbers.** Leading minus everywhere (no parentheses seen). En-dash minus in "–3 743 MMAD" (p. 24 footnote). Minus sign on a separate line from the number in the p. 46 movement table ("-" then "409"; "- 5 247" with a space). Labels carrying "(-)" next to already-negative values ("Dépréciations (-)  -97", p. 51). Same item with opposite signs in different places (company IS "2 400 505" p. 81 vs "-2 401" p. 82; D&A positive in Note 22, negative in P&L). Net debt shown as negative "Trésorerie nette -17 610" (p. 56) and positive "Dette Nette 17 610" (p. 9).
4. **Footnote markers glued to text and numbers.** "CAPEX(2)", "Parc(8)", "chiffre d'affaires(4)", "Variation à change constant (1)", "Capital social ou personnel (1)", "Sotelma*", "MT CASH **", "UNI TOWER***". Risk of reading "(2)" as a value. Superscript "er" in "1er" (p. 7). A number split across a line break: "8\n022 millions" (p. 10).
5. **Merged / multi-level headers.** p. 15 Annexes (2024 / 2025 over Maroc / Filiales / Groupe); p. 64 Note 27 (De base / dilué under each year); pp. 83-84 ("NET" over 2023/2024/2025); p. 79 (BRUT / AMORTISSEMENTS ET PROVISIONS / NET / NET 31/12/2024); p. 81 (OPERATIONS Propres à l'exercice / Exercices précédents); pp. 9, 12, 19 (two side-by-side blocks T4 and 12M, each with Variation columns); p. 40 Note 2 (company name row, then 3 date sub-rows, then an address row).
6. **Wrong or duplicate headers.** p. 23 asset block header reads "Créances d'exploitation et autres" instead of "ACTIF (en millions MAD)". p. 68 currency table header "31-déc.-24 | 31-déc.-24 | 31-déc.-25" (first should be 23). Notes start at sub-number 24.2, 28.2, 30.2 (no .1). Note 1 numbering jumps (1.2, 2.1.1, 2.2).
7. **Internal inconsistencies to flag, not resolve.** 12M 2024 revenue 36 704 (p. 9) vs 36 699 (p. 24); Maroc 2024 revenue 19 148 (p. 11) vs 19 143 (p. 59); RNPG 6 969 / 1 792 (pp. 9, 15) vs 6 968 / 1 801 (p. 24); tax reconciliation "Impôts comptabilisés" 4 618 / 2 181 (p. 63) vs 4 610 / 2 291 (p. 24); Sotelma equity impact "289 millions" (p. 7) vs -299 / +289 in the equity table (p. 26); CAPEX 2024 11 164 (p. 9) vs 11 163 (p. 65); minority dividends 746 / 831 (cash flow) vs 748 / 827 (Note 13); 2024 Moov mobile base 51 191 (p. 13, restated) vs 56 376 (p. 20); MT CASH shown as IG in 2023-2024 (p. 40) while consolidated only from Q4 2025; p. 59 "augmenté de 7% par rapport à 2025" (should be 2024); p. 9 net debt "Variation 21,5%" positive for a decrease.
8. **Decimal separators.** Comma is standard ("7,93", "10,7065") but points appear in text: "199.5 millions" (p. 44), "6.4 milliards" (p. 60), "0.5 milliard" (p. 61). An odd cell "6,10" in the 2024 intangibles amortisation "Cessions" column (p. 44) and "0,40" / "0,10" / "0,30" in p. 46 - UNCERTAIN meaning.
9. **Placeholder tokens.** "NS", "N.S", "NA", "-" (blank or zero), empty cells; "NS" used as a % value in Note 7.1.
10. **Implicit periods.** Company-only columns labelled only "EXERCICE" (current year implied 2025) vs "EXERCICE PRECEDENT NET 31/12/2024"; consolidated "31-déc.-25", "12M 2025", "T4 2025", "Exercice 2025", "31/12/2025"; CMC closes on 31 March (p. 28).
11. **Governance wording conflict.** p. 90 back cover: "Société Anonyme à Directoire et Conseil de Surveillance"; pp. 10, 28: "Conseil d'Administration"; p. 16 (FY2024 text): "Conseil de Surveillance". A board-seat extractor must not infer the board type from p. 90.
12. **Entity resolution.** Maroc Telecom = IAM = Itissalat Al-Maghrib; Wana = Wana Corporate = WANA CORPORATE = INWI (p. 62, alias decided 2026-10-29); Etisalat = Emirates Telecommunications Corporation; Etat Marocain = Royaume du Maroc; country names used as entity names ("Mauritanie", "Mali") in KPI tables; Mauritel appears only in text (Note 2 lists the holding CMC instead); "Autres" means free float in p. 27 but "other Etisalat sister companies" in p. 67.
13. **Control vs ownership.** Sotelma is fully consolidated at 44% (control via shareholders' pact); Mauritel at 41,2% interest / 51,5% voting rights.
14. **Bullets in non-ASCII glyphs.** "►", "➢", "✓", "▪" used as list markers (pp. 34, 38, 62, 82).

## 8. Test questions

| # | Type | Question | Expected answer | Citation |
|---|---|---|---|---|
| Q1 | text (outlook) | What does Maroc Telecom forecast for 2026? | At constant scope and exchange rates, absent a major exceptional event: growth in revenue and EBITDA, and CAPEX of about 25% of revenue excluding frequencies and licences. | p. 10, "Perspectives du Groupe Maroc Telecom pour l'année 2026" |
| Q2 | text (risks) | Which market risks does the group describe, and what is the impact of a 1% depreciation of the dirham against the euro? | Credit, foreign exchange, liquidity and interest-rate risk. A 1% MAD depreciation vs EUR: revenue +190 MAD m, operating result +49 MAD m, net income group share +20 MAD m. | pp. 68-70, Note 32; quoted p. 69 "Chiffre d'affaires = +190 millions de dirhams" |
| Q3 | text (strategy / events) | What happened with the Wana Corporate dispute in 2025 and how did it affect results? | The unbundling disputes with Wana Corporate were closed in H1 2025 with a positive impact of 2 billion MAD (retrocession), lifting reported EBITA to 13 547 MAD m (adjusted 11 547). | p. 68 Note 31.3; p. 10; p. 15 Annexe 1 row "Litige Wana Corporate" 2 000 |
| Q4 | text (related parties) | With which related parties did Maroc Telecom transact in 2025, and how much revenue came from Etisalat? | Emirates Telecommunications Corporation (Etisalat), EDCH, Etihad Etisalat Company (Mobily) and other sister companies; revenue from Etisalat 275 MAD m. | p. 66 §30.4; p. 67 table Exercice 2025, row Chiffre d'affaires, col Etisalat |
| Q5 | figure | What was consolidated revenue (IFRS) for FY2025? | 36 681 MAD millions (36,681 bn MAD); FY2024: 36 699. | p. 24, ÉTAT DE RÉSULTAT GLOBAL, row Chiffre d'affaires, col 31-déc.-25 |
| Q6 | figure | What was consolidated net debt at 31 Dec 2025 and the net debt / EBITDA ratio? | 17 610 MAD millions (written "Trésorerie nette -17 610" in Note 15.1); ratio 0,9x (excl. IFRS 16). | p. 56 Note 15.1 row Trésorerie nette; p. 9 rows Dette Nette, Dette Nette/EBITDA(3) |
| Q7 | figure | What was FY2025 net income attributable to the group? | 6 968 MAD millions (p. 24); the management tables round to 6 969 (pp. 9-10). Adjusted: 5 649. | p. 24 row Part du groupe; p. 9 |
| Q8 | figure | What was Maroc Telecom's company-only (CGNC) net income for 2025? | 5 805 375 thousand MAD (about 5 805 MAD m); 2024: 1 592 703 thousand. | p. 81 row "XIII- RESULTAT NET XI - XII"; p. 85 auditors' opinion |
| Q9 | graph | Who are Maroc Telecom's shareholders at 31 Dec 2025? | Etisalat 53%, Royaume du Maroc 22%, Autres (free float) 25%, of 879 095 340 shares. | p. 27 |
| Q10 | graph | Which fully consolidated subsidiaries are not wholly owned, and what is the interest? | CMC 80%, Onatel 61%, Gabon Telecom 51%, Sotelma 44%, Moov Africa Côte d'Ivoire 85%, Moov Africa Togo 95% (Mauritel 41,2% through CMC, p. 7). | p. 40 Note 2; p. 63 Note 26 lists the same minority set |
| Q11 | not answerable | What was Maroc Telecom's share price or market capitalisation at 31 Dec 2025? | Not in this document. | n/a |
| Q12 | not answerable | Who is the chairman of the board / CEO of Maroc Telecom? | Not in this document (only two directors are named, in the co-optation on p. 10). | n/a |

## 9. NOTES

**Status: golden v0 (accepted 2026-10-29). Read once, not yet verified value by value; see the header for how disagreements are handled.**

What I could not read:
- p. 26 (equity movements) has no text layer; the few values used (e.g. "Opérations sur actions propres" 30 / -35, Sotelma -299 / 289) were read from the rendered page image and are marked UNCERTAIN.
- p. 58 (15.3 Tableau d'analyse of borrowings by lender) is unreadable without high-resolution OCR; no figures or lender entities were taken from it.
- The PDF does not contain: the ETIC notes to the company-only accounts, the état des soldes de gestion, the tableau de financement, the auditors' special report on regulated agreements, any ISIN / ticker, any share price, any dividend payment date, any treasury share count.
- Tooling: `pdftotext` is not installed (not installed per instructions); the PDF was read with the Read tool, which returned the text layer plus page images. No independent second extraction was possible, so every value depends on one reading.

Verify first (highest risk):
1. All values in figures.csv against the page images, especially company-only thousands (pp. 79-81) and the sign of negative values.
2. Remaining UNCERTAIN items: holder of SH22-SH36; company dividends "1,3 milliards" (p. 84). Decided 2026-10-29: "Autres" = free float (SH3); no SPT -> Etisalat link (SH4); INWI = Wana Corporate.
3. Which figure is authoritative where the document disagrees with itself (Hard case 7), e.g. RNPG 6 968 vs 6 969, revenue 2024 36 699 vs 36 704.
4. Auditor-opinion classification: decided 2026-10-29, an "Observation" paragraph maps to "emphasis of matter".
5. Cross-reference X12 ("note 31.4") points to a note that does not exist.

Estimated completeness:
- Entities: about 90% of named organisations and persons (banks in the p. 58 loan table excluded).
- Shareholding, consolidation, board, audit, dividend, opinion, related-party facts: about 95% of what the document states.
- Financial figures: all required line items covered for FY2025 and FY2024 where the document has them; 160 rows is a curated subset (not every note row was extracted, e.g. Note 4/5 movement tables, provisions, segment balance sheets, FY2023 columns, EUR tables).
- Overall: roughly 80% of a full golden set; the remaining work is the p. 26 / p. 58 OCR and human verification.
