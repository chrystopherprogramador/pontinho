# 🃏 Pontinho Vegas

Placar de Pontinho (Vegas Edition) com ranking global em SQLite e backend Flask.

## Estrutura

```
.
├── app.py                  # Backend Flask + SQLite
├── templates/index.html    # Frontend (single page)
├── static/
│   ├── icon.svg            # Favicon / ícone PWA
│   ├── manifest.webmanifest
│   └── sw.js               # Service worker (PWA)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .dockerignore
```

## Rodar localmente (sem Docker)

```powershell
python -m pip install -r requirements.txt
python app.py
# http://127.0.0.1:5000
```

## Rodar com Docker Compose (recomendado pra servidor)

```bash
docker compose up -d --build
```

- Servidor em `http://<host>:5000`
- Banco persistido no volume `pontinho_data` (mapeado em `/app/data/pontinho.db` dentro do container)
- Healthcheck automático em `/api/ranking`
- `restart: unless-stopped` — sobe sozinho após reboot

### Comandos úteis

```bash
docker compose logs -f pontinho      # ver logs
docker compose down                  # parar (mantém volume/dados)
docker compose down -v               # parar e apagar dados
docker compose pull && docker compose up -d --build   # atualizar
```

### Backup do banco

Via API (qualquer hora):
```bash
curl -o backup.db http://<host>:5000/api/export
```

Direto do volume:
```bash
docker compose cp pontinho:/app/data/pontinho.db ./backup.db
```

## Salas (multi-liga)

Cada partida pode pertencer a uma sala isolada. Basta acessar com `?sala=nome`:
- `http://<host>:5000/?sala=familia`
- `http://<host>:5000/?sala=trabalho`

Rankings, stats e jogadores são separados por sala. Sem `?sala=`, cai em `global`.

## Variáveis de ambiente

| Variável        | Default                  | Descrição                      |
|-----------------|--------------------------|--------------------------------|
| `PONTINHO_DB`   | `/app/data/pontinho.db`  | Caminho do arquivo SQLite      |
| `TZ`            | `America/Sao_Paulo`      | Fuso pra exibir datas no host  |

## Reverse proxy (Nginx / Caddy)

Caddy (1 linha):
```
pontinho.seudominio.com {
    reverse_proxy localhost:5000
}
```

Nginx (resumo):
```nginx
server {
    listen 80;
    server_name pontinho.seudominio.com;
    location / { proxy_pass http://127.0.0.1:5000; }
}
```

## Endpoints

- `GET  /` — app
- `GET  /api/ranking?sala=...` — ranking da sala
- `GET  /api/players?sala=...` — autocomplete
- `GET  /api/stats/<nome>?sala=...` — estatísticas detalhadas
- `GET  /api/matches?sala=...` — últimas partidas
- `POST /api/match?sala=...` — grava partida (chamado pelo front)
- `GET  /api/rooms` — lista salas existentes
- `GET  /api/export` — download do `.db`
