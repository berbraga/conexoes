# LinkedIn Auto Connect

Automação em Python para enviar convites de conexão no LinkedIn de forma agendada, com interface web simples e execução 100% dentro de Docker.

## Funcionalidades

- Interface web para configurar dias da semana, horário, URL de busca e mensagem personalizada
- Mensagem com parâmetro dinâmico `{nome}` (primeiro nome do perfil)
- Login via cookie `li_at` (sem usuário/senha)
- Limites diários e semanais configuráveis
- Delays aleatórios entre ações para simular comportamento humano
- Deduplicação de convites via SQLite
- Agendamento automático com APScheduler

## Requisitos

- Docker
- Docker Compose

## Como obter o cookie `li_at`

1. Acesse [linkedin.com](https://www.linkedin.com) e faça login normalmente no navegador
2. Abra as ferramentas de desenvolvedor (F12)
3. Vá em **Application** (Chrome) ou **Armazenamento** (Firefox) → **Cookies** → `https://www.linkedin.com`
4. Copie o valor do cookie chamado `li_at`
5. Cole na interface da automação

> O cookie expira periodicamente. Se a automação falhar com "sessão expirada", gere um novo cookie.

## Deploy na VPS

```bash
# Clone o repositório na VPS
git clone <seu-repositorio> linkedin-connect
cd linkedin-connect

# Suba o container
docker compose up -d --build

# Acesse a interface
# http://<ip-da-vps>:8000
```

Os dados (configuração e banco SQLite) ficam persistidos em `./data`.

## Uso

1. Acesse a interface em `http://localhost:8000` (ou IP da VPS)
2. Cole o cookie `li_at`
3. Selecione os dias da semana e o horário de execução
4. Cole a URL de uma busca de pessoas do LinkedIn, por exemplo:
   `https://www.linkedin.com/search/results/people/?keywords=desenvolvedor`
5. Configure a mensagem da nota usando `{nome}` como placeholder
6. Ajuste os limites de segurança (recomendado: 15/dia, 100/semana)
7. Salve as configurações
8. Use **Executar agora** para testar ou ative o **agendamento automático**

A execução termina quando:
- Todos os perfis da busca foram processados
- O limite diário ou semanal é atingido
- Você clica em **Parar execução**

## Comandos úteis

```bash
# Ver logs
docker compose logs -f

# Parar
docker compose down

# Rebuild após alterações
docker compose up -d --build
```

## Estrutura do projeto

```
app/
  main.py              # FastAPI + rotas da interface
  config.py            # Configurações persistidas
  scheduler.py         # Agendamento e controle do worker
  linkedin/
    client.py          # Sessão Playwright + cookie
    connector.py       # Lógica de envio de convites
    humanizer.py       # Delays e limites anti-ban
  storage/
    db.py              # SQLite (convites + logs)
  templates/
  static/
data/                  # Volume Docker (config + banco)
```

## Aviso legal

Automatizar ações no LinkedIn pode violar os Termos de Uso da plataforma e resultar em restrições ou banimento da conta. Use limites conservadores e por sua conta e risco.
