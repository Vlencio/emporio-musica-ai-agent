from anthropic import beta_tool
import re
import json
from config import DB_PATH
import sqlite3
from typing import Optional



def _digits(phone: str) -> str:
    return re.sub(r"\D", "", phone)

def _emails(email: str) -> str:
    return email.lower().strip()

@beta_tool
def get_order(phone: str, email: str) -> str:
    """Busca os pedidos de um cliente, do mais recente para o mais antigo.

    Use quando o cliente perguntar sobre status, rastreio, prazo de entrega
    ou itens de um pedido. Exige celular e e-mail para confirmar a identidade.

    Args:
        phone: Celular do cliente, em qualquer formato (ex: (34) 99999-0000).
        email: E-mail cadastrado do cliente.
    """
    con = sqlite3.connect(DB_PATH)
    try:
        con.create_function("digits", 1, _digits)
        con.create_function("emails", 1, _emails)

        orders_query = '''
            SELECT json_object(
                'order_id', o.order_id,
                'order_date', o.order_date,
                'order_status', o.status,
                'order_total_brl', o.total_brl,
                'order_payment_method', o.payment_method,
                'order_tracking_code', o.tracking_code,
                'order_estimated_delivery', o.estimated_delivery,
                'order_notes', o.notes,
                'items', json_group_array(
                    json_object('product_name', p.name, 'quantity', oi.quantity)
                )
            ) AS order_json
            FROM orders o
            JOIN customers c    ON c.customer_id = o.customer_id
            JOIN order_items oi ON oi.order_id = o.order_id
            JOIN products p     ON p.product_id = oi.product_id
            WHERE digits(c.phone) = ? AND emails(c.email) = ?
            GROUP BY o.order_id
            ORDER BY o.order_date DESC
        '''

        query = f'SELECT json_group_array(json(order_json)) FROM ({orders_query})'
        result = con.execute(query, (_digits(phone), _emails(email))).fetchone()[0]

    finally:
        con.close()

    if result == "[]":
        return json.dumps({"error": "Nenhum pedido encontrado para este email e celular."})
    return result

@beta_tool
def get_products(
    name: Optional[str] = None,
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    in_stock_only: bool = False,
) -> str:
    """Busca instrumentos no catálogo. Todos os filtros são opcionais e combináveis.

    Args:
        name: Parte do nome do produto ou marca (ex.: "Takamine", "GD20").
        category: Categoria: Guitarras, Baixos, Baterias e Percussão, Teclados e Pianos, Violões ou Ukuleles.
        min_price: Preço mínimo em reais.
        max_price: Preço máximo em reais.
        in_stock_only: Se true, retorna só produtos ativos com estoque.
    """
    
    base_query = '''
        SELECT json_object(
            'product_id', p.product_id,
            'name', p.name,
            'category', c.name,
            'description', p.description,
            'price_brl', p.price_brl,
            'stock_quantity', p.stock_quantity,
            'status', p.status,
            'specs', json(p.specs),
            'promotion', pr.description,
            'discount_percent', pr.discount_percent,
            'promo_price_brl', ROUND(p.price_brl * (1 - pr.discount_percent / 100.0), 2)
        ) AS product_json
        FROM products p
        JOIN categories c ON c.category_id = p.category_id
        LEFT JOIN promotions pr ON pr.product_id = p.product_id AND pr.is_active = 1
    '''

    conditions, params = [], []

    if name:
        conditions.append("p.name LIKE ?")
        params.append(f"%{name}%")
    if category:
        conditions.append("c.name LIKE ?")
        params.append(f"%{category}%")
    if min_price is not None:
        conditions.append("p.price_brl >= ?")
        params.append(min_price)
    if max_price is not None:
        conditions.append("p.price_brl <= ?")
        params.append(max_price)
    if in_stock_only:
        conditions.append("p.status = 'active' AND p.stock_quantity > 0")

    if conditions:
        base_query += " WHERE " + " AND ".join(conditions)
    base_query += " ORDER BY p.price_brl"

    products_query = base_query

    try:
        con = sqlite3.connect(DB_PATH)

        query = f'SELECT json_group_array(json(product_json)) FROM ({products_query})'
        result = con.execute(query, params).fetchone()[0]

        if result == "[]":
            categories = [row[0] for row in con.execute(
                """ 
                SELECT c.name FROM categories c
                JOIN products p ON p.category_id = c.category_id
                WHERE p.status = 'active'
                GROUP BY c.name ORDER BY c.name
                """
            )]

            return json.dumps({
                "error": "nenhum produto encontrado",
                "available_categories": categories
            }, ensure_ascii=False)   

    finally:
        con.close()
    return result



TOOLS = [get_order, get_products]


