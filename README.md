# Majority Colouring

## Windows setup
1. Install Julia (e.g., via juliaup) and ensure `julia` is on your PATH.
2. (Optional) Install Jupyter: `pip install notebook` (or `pip install jupyterlab`).
3. Open PowerShell and run:
   `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`
4. From the repository root, run:
   `.\setup.ps1` (optionally `.\setup.ps1 "KernelName"`).
5. Start Jupyter with `jupyter notebook` and select the `MajorityColoring` kernel (or your custom name).

## Linux setup
1. Install Julia (e.g., via juliaup) and ensure `julia` is on your PATH.
2. (Optional) Install Jupyter: `pip install notebook` (or `pip install jupyterlab`).
3. From the repository root, run:
   `./setup.sh` (optionally `./setup.sh "KernelName"`).
4. Start Jupyter with `jupyter notebook` and select the `MajorityColoring` kernel (or your custom name).

## Python setup (charts)
1. Init & activate virtual env: `python3 -m venv .venv && source .venv/bin/activate`
2. Install requirements: `pip install -r requirements.txt`