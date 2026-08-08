@echo off
venv\Scripts\python.exe manage.py makemigrations master_setup
venv\Scripts\python.exe manage.py makemigrations organizations
