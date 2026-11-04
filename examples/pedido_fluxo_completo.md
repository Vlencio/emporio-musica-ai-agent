# pedido_fluxo_completo (pedidos)

**user:** Quero saber do meu pedido

**assistant:** Oi! Claro, posso te ajudar com isso. Pra consultar seu pedido, preciso que você me informe:

1. Seu celular cadastrado
2. Seu e-mail cadastrado

Assim que você mandar, eu busco as informações pra você.

**user:** Meu celular é (67) 99654-7821 e o e-mail anacarol.ferreira@coldmail.com

*[tool_use]* `get_order` {"phone": "(67) 99654-7821", "email": "anacarol.ferreira@coldmail.com"}

*[tool_result]* [{"order_id":8,"order_date":"2026-02-15","order_status":"shipped","order_total_brl":349.9,"order_payment_method":"debit","order_tracking_code":"BRJL5544332BR","order_estimated_delivery":"2026-02-28","order_notes":null,"items":[{"product_name":"Kala KA-C Concert Mogno","quantity":1}]}]

**assistant:** Encontrei o seu pedido:

- **Pedido nº 8**, feito em 15/02/2026
- **Item:** Kala KA-C Concert Mogno (1 unidade)
- **Valor:** R$ 349,90, pago no débito
- **Status:** enviado
- **Código de rastreio:** BRJL5544332BR (dá pra acompanhar no site dos Correios ou da Jadlog)
- **Previsão de entrega:** 28/02/2026

Essa previsão já passou e o sistema ainda mostra como enviado. Pode ser que você já tenha recebido e o status não tenha sido atualizado. Se ainda não chegou, fala com a gente pelo WhatsApp (67) 3321-4500 que a equipe verifica com a transportadora.
