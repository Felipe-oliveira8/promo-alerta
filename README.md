# Promo Alerta 🔥

Robô pessoal que lê canais de promoção do Telegram a cada 10 minutos e te
avisa no seu Telegram quando aparece algo que casa com seus alertas.
Roda de graça no GitHub Actions — não precisa deixar o PC ligado.

Canais iniciais: @pelandobr, @cupons_desconto (Promobit), @achadosdotb, @ofertaskabum.

---

## Instalação (≈ 15 minutos, sem instalar nada no PC)

### 1. Crie o bot no Telegram
1. No Telegram, abra **@BotFather** → `/newbot` → escolha nome e usuário.
2. Guarde o **token** (algo como `123456789:ABC...`).
3. Abra a conversa com seu bot novo e toque em **Iniciar** (ou mande "oi").
4. No navegador, abra (trocando `<TOKEN>`):
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   Procure `"chat":{"id":` — esse número é o seu **chat id**.

### 2. Gere a chave que criptografa seus alertas
No navegador, aperte **F12 → Console**, cole e dê Enter:
```js
btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(32)))).replace(/\+/g,'-').replace(/\//g,'_')
```
Copie o texto que aparecer (44 caracteres, termina com `=`). Essa é a **CHAVE_ALERTAS**.
Guarde num lugar seguro: sem ela, os alertas salvos não podem ser lidos.

### 3. Crie o repositório no GitHub
1. Em github.com → **New repository** → nome `promo-alerta` → **Public** → Create.
2. **Add file → Upload files** e envie todos os arquivos desta pasta
   (`main.py`, `comandos.py`, `estado.py`, `filtro.py`, `fontes.py`,
   `telegram_bot.py`, `config.json`, `requirements.txt`, `.gitignore`, `README.md`, `tests/`).
3. O workflow fica numa pasta oculta, então crie-o à mão:
   **Add file → Create new file**, no nome digite
   `.github/workflows/promo-alerta.yml` e cole o conteúdo do arquivo de mesmo nome.

> O repositório é público, mas **nada sensível fica exposto**: o token e a chave
> ficam nos Secrets, e seus alertas são salvos criptografados (`dados/alertas.enc`).

### 4. Cadastre os Secrets
No repositório: **Settings → Secrets and variables → Actions → New repository secret**.
Crie os três:

| Nome | Valor |
|---|---|
| `TELEGRAM_TOKEN` | token do passo 1 |
| `TELEGRAM_CHAT_ID` | chat id do passo 1 |
| `CHAVE_ALERTAS` | chave do passo 2 |

### 5. Rode pela primeira vez
Aba **Actions** → **Promo Alerta** → **Run workflow**.
Em ~1 minuto chega no Telegram: *"✅ Promo Alerta instalado e funcionando!"*.
A partir daí ele roda sozinho a cada 10 minutos.

---

## Uso no dia a dia (pelo Telegram)

| Comando | O que faz |
|---|---|
| `/add "air fryer" -forma max 450` | cria alerta |
| `/lista` | mostra seus alertas numerados |
| `/remover 2` | apaga o alerta 2 |
| `/pausar 2` · `/ativar 2` | pausa / retoma |
| `/preco 2 6m` | valor justo e histórico de preço do alerta 2 (`30d`, `3m`, `6m`, `1a`) |
| `/preco "5060 ti" 16gb 1a` | o mesmo, para qualquer produto (sem criar alerta) |
| `/canais` | canais monitorados |
| `/addcanal @canal` · `/rmcanal @canal` | muda os canais |
| `/ajuda` | lista de comandos |

**Como escrever um alerta**
- palavras soltas → todas precisam aparecer (`iphone 15 128gb`)
- `"entre aspas"` → expressão exata (`"air fryer"`)
- `a|b|c` → pelo menos uma delas (`mondial|philco|electrolux`)
- `-palavra` → não pode aparecer (`-capa -pelicula`)
- `max 400` (ou `ate 400`, `<=400`) → só se tiver preço até R$ 400
- Maiúsculas, acentos, hífens e espaços entre letras e números não importam:
  `"5060 ti"` também pega "RTX5060Ti", "5060-Ti" e "5060TI"; `16gb` pega "16 GB".

**Como o /preco calcula**
Busca as ofertas antigas do produto nos canais monitorados e mostra:
valor justo (mediana: metade das promoções saiu abaixo disso), bom preço
(o valor das 25% mais baratas), mínimo, média, máximo, última oferta e a mediana
de cada mês. São preços de **promoções postadas nos canais**, não o preço normal
de loja. Parcelas, cupons e valores fora da curva são descartados, e a mesma oferta
postada em dois canais no mesmo dia conta uma vez só.

Ao criar um alerta, ele também confere as postagens que já estão nos canais e
manda até 5 resultados recentes, para você ver na hora se o filtro está bom.

> ⏱️ O robô não fica ligado o tempo todo: comandos e alertas chegam na próxima
> rodada (até ~10 min; em horários de pico o GitHub pode atrasar um pouco mais).

---

## Bom saber
- **Custo:** zero. GitHub Actions é gratuito e ilimitado em repositório público.
- **Segurança:** o bot só obedece ao seu chat id; mensagens de outras pessoas são ignoradas.
- **Canal com problema:** se um canal ficar ~1h sem conseguir ser lido, o bot te avisa.
- **Inatividade:** o GitHub desliga agendamentos de repositórios públicos parados há
  60 dias. O robô regrava o arquivo de alertas a cada 30 dias para evitar isso.
  Se mesmo assim desligar, é só reativar na aba Actions.
- **Antes de comprar:** o alerta é só um aviso — confira loja, vendedor, frete e preço final.

## Testar no PC (opcional)
```bash
pip install -r requirements.txt
cp .env.example .env        # preencha token e chat id (CHAVE_ALERTAS pode ficar vazia)
python main.py --simular    # mostra no terminal o que enviaria, sem enviar
python -m pytest tests      # testes automáticos
```
