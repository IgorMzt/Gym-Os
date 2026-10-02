# Instalação

## Windows — desenvolvimento/local

1. Instale Python 3.11 64-bit, Git e Docker Desktop (se usar PostgreSQL local).
2. Crie e ative o ambiente:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
.\install_windows.ps1
```

3. Crie a configuração local:

```powershell
Copy-Item .env.example .env
```

4. Para PostgreSQL local:

```powershell
docker compose -f compose.postgres.yml up -d
```

Configure no `.env`:

```env
DATABASE_BACKEND=postgresql
DATABASE_URL=postgresql://gymos:gymos_dev@127.0.0.1:5432/gymos
```

5. Inicialize e valide:

```powershell
python manage.py check-config
python manage.py init-db
python manage.py db-status
python -m pytest -q
python app.py
```

## SQLite

SQLite permanece disponível para desenvolvimento/compatibilidade. Use `DATABASE_BACKEND=sqlite`. Para implantação cloud, prefira PostgreSQL.

## Reconhecimento facial no Windows

O projeto usa `dlib-bin` e instala `face-recognition` separadamente via `install_windows.ps1`. Se bibliotecas nativas falharem em caminhos Windows com caracteres especiais, execute o projeto por um caminho ASCII estável (por exemplo, uma junction), sem duplicar o repositório.
