# Terminal Commands

Quick reference for all terminal commands used in this project.

---

## 🚀 Setup & Installation

### Create Virtual Environment
```bash
python3 -m venv venv
```

### Activate Virtual Environment
```bash
source venv/bin/activate
```

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Upgrade pip (if needed)
```bash
pip install --upgrade pip
```

### Verify Package Installation
```bash
python test_setup.py
```

---

## ▶️ Running the Application

### Run Main Application
```bash
PYTHONPATH=. python src/main.py
```

Or use the module syntax:
```bash
python -m src.main
```

---

## 🧪 Testing

### Run All Tests
```bash
PYTHONPATH=. pytest
```

### Run Tests with Coverage
```bash
PYTHONPATH=. pytest --cov=src
```

### Run Specific Test File
```bash
PYTHONPATH=. pytest tests/test_trade_execution.py
```

### Run Tests with Verbose Output
```bash
PYTHONPATH=. pytest -v
```

---

## 🔧 Development

### Check Installed Packages
```bash
pip list
```

### Freeze Current Dependencies
```bash
pip freeze > requirements.txt
```

### Install a Specific Package
```bash
pip install <package_name>
```

### Uninstall a Package
```bash
pip uninstall <package_name>
```

---

## 🗄️ Database (Alembic Migrations)

### Initialize Alembic
```bash
alembic init alembic
```

### Create a Migration
```bash
alembic revision --autogenerate -m "description"
```

### Run Migrations
```bash
alembic upgrade head
```

### Downgrade Migration
```bash
alembic downgrade -1
```

---

## 📊 Jupyter Notebook (Optional)

### Install Jupyter
```bash
pip install jupyter
```

### Start Jupyter Notebook
```bash
jupyter notebook
```

---

## 🔍 Debugging

### Run Python Interactive Shell
```bash
python
```

### Check Python Version
```bash
python --version
```

### Check Module Location
```bash
python -c "import <module>; print(<module>.__file__)"
```

---

## 💡 Common Issues

### Module Not Found Error
If you see `ModuleNotFoundError: No module named 'src'`, use one of these methods:

**Option 1: Set PYTHONPATH**
```bash
PYTHONPATH=. python src/main.py
```

**Option 2: Use module syntax**
```bash
python -m src.main
```

**Option 3: Export PYTHONPATH (permanent for session)**
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
python src/main.py
```

### Deactivate Virtual Environment
```bash
deactivate
```

---

## 📋 Quick Start (Copy & Paste)

```bash
# Full setup from scratch
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python test_setup.py
PYTHONPATH=. python src/main.py
```
