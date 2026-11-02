PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS categories (
    category_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    city TEXT
);

CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY,
    price_brl REAL NOT NULL,
    name TEXT NOT NULL,
    category_id INT NOT NULL REFERENCES categories(category_id),
    description TEXT,
    stock_quantity INT NOT NULL,
    status TEXT,
    specs TEXT CHECK(specs IS NULL OR json_valid(specs)),
    created_at DATE
);

CREATE TABLE IF NOT EXISTS orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INT NOT NULL REFERENCES customers(customer_id),
    order_date DATE NOT NULL,
    status TEXT,
    total_brl REAL NOT NULL,
    payment_method TEXT NOT NULL,
    tracking_code TEXT,
    estimated_delivery DATE,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS order_items (
    order_id INT NOT NULL REFERENCES orders(order_id),
    quantity INT NOT NULL CHECK(quantity > 0),
    product_id INT NOT NULL REFERENCES products(product_id),
    PRIMARY KEY (order_id, product_id)
);

CREATE TABLE IF NOT EXISTS promotions (
    promotion_id INTEGER PRIMARY KEY,
    product_id INT NOT NULL REFERENCES products(product_id),
    discount_percent INT NOT NULL CHECK(discount_percent > 0 AND discount_percent <= 100),
    description TEXT NOT NULL,
    is_active INT NOT NULL
);