
# 🎓 Scholarship Intelligence Crawler

An automated scholarship discovery, extraction, verification, and monitoring system built with Python, SQLite, BeautifulSoup, Requests, and Streamlit.

The system discovers scholarship opportunities from web sources, extracts relevant information, stores structured records in a database, tracks changes, and provides a dashboard to inspect scholarship information and crawler activity.


## Overview

Finding scholarships can be difficult because information is spread across government portals, educational institutions, foundations, NGOs, and corporate websites.

The Scholarship Intelligence Crawler automates parts of this process by collecting scholarship information from web pages and organizing it into a searchable database.


The application provides a Streamlit dashboard for running crawls and viewing collected information.

**Important:** Automated extraction and domain classification do not independently prove that a scholarship is genuine. Records should be verified against their original sources.



## 2. Technology Stack

| Technology | Purpose |
|---|---|
| Python | Core application logic |
| Requests | HTTP requests to web pages |
| BeautifulSoup | HTML parsing and link extraction |
| SQLite | Persistent data storage |
| Streamlit | Interactive dashboard |
| Hashing | Content comparison and change detection |
| Pytest | Automated testing |

---

## 3. Project Structure

```text
Scholarship-crawl/
│
├── data/
│   └── scholarships.db
│
├── src/
│   ├── __init__.py
│   ├── change_detector.py
│   ├── database.py
│   ├── discovery.py
│   ├── extractor.py
│   └── verifier.py
│
├── tests/
│   ├── test_database.py
│   ├── test_extractor.py
│   ├── test_verifier.py
│   └── test_database_migration.py
│
├── app.py
├── config.py
├── requirements.txt
├── .env
├── .gitignore
└── README.md
```

The exact files in the local project may differ slightly depending on the version being used.

### Important files

**app.py**
- Starts the Streamlit dashboard.
- Displays controls and scholarship metrics.
- Allows the user to initiate a crawler run.

**src/discovery.py**
- Finds candidate scholarship URLs from configured sources.

**src/extractor.py**
- Parses webpage content.
- Extracts structured scholarship fields.

**src/verifier.py**
- Classifies source domains.
- Evaluates available evidence and verification information.

**src/change_detector.py**
- Compares extracted records with existing database records.
- Tracks changes and repeated verification failures.

**src/database.py**
- Initializes the SQLite database.
- Creates tables and indexes.
- Stores and retrieves scholarship records.
- Provides dashboard metrics.
- Migrates older database schemas when required.

**config.py**
- Contains crawler configuration, paths, and operational settings.

**requirements.txt**
- Lists Python dependencies.

---



## 4. Installation

### Prerequisites

Install the following:

- Python 3.10 or a compatible version supported by the dependencies
- pip
- Git (optional)

Check your Python installation:

```powershell
python --version
```

Check pip:

```powershell
python -m pip --version
```

### Step 1: Open the Project Folder

Open PowerShell or the VS Code terminal inside the project directory.

For example:

```powershell
cd "C:\Users\dhurv\Desktop\Scholarship-crawl"
```

Replace this path if your project is stored somewhere else.

### Step 2: Create a Virtual Environment

```powershell
python -m venv venv
```

### Step 3: Activate the Virtual Environment

```powershell
.\venv\Scripts\Activate.ps1
```

If PowerShell blocks script execution, use Command Prompt instead:

```cmd
venv\Scripts\activate.bat
```

### Step 4: Install Dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## 5. Running the Application

### Option A: Start the Dashboard

From the project root directory:

```powershell
streamlit run app.py
```

Streamlit will print a local URL, usually:

```text
http://localhost:8501
```

Open that URL in your browser.

