CREATE SCHEMA IF NOT EXISTS service;

CREATE TABLE IF NOT EXISTS service.customers (
    customer_id INTEGER PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    city VARCHAR(80),
    region VARCHAR(40)
);

CREATE TABLE IF NOT EXISTS service.assets (
    asset_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES service.customers(customer_id),
    tag VARCHAR(40) UNIQUE NOT NULL,
    asset_type VARCHAR(60),
    status VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS service.work_orders (
    work_order_id INTEGER PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES service.assets(asset_id),
    technician VARCHAR(100),
    summary VARCHAR(200),
    status VARCHAR(20),
    priority INTEGER,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_work_orders_status_priority
    ON service.work_orders(status, priority);

CREATE OR REPLACE VIEW service.open_work_orders AS
SELECT w.work_order_id, a.tag, c.name AS customer, w.technician,
       w.summary, w.priority
FROM service.work_orders w
JOIN service.assets a ON a.asset_id = w.asset_id
JOIN service.customers c ON c.customer_id = a.customer_id
WHERE w.status = 'open';

DELETE FROM service.work_orders;
DELETE FROM service.assets;
DELETE FROM service.customers;

INSERT INTO service.customers VALUES
    (1, 'Northwind Field Lab', 'Toronto', 'ON'),
    (2, 'Contoso Water', 'Hamilton', 'ON'),
    (3, 'Adventure Works Mining', 'Sudbury', 'ON');

INSERT INTO service.assets VALUES
    (101, 1, 'PUMP-101', 'centrifugal-pump', 'active'),
    (102, 1, 'VALVE-102', 'control-valve', 'maintenance'),
    (201, 2, 'METER-201', 'flow-meter', 'active'),
    (301, 3, 'FAN-301', 'ventilation-fan', 'active');

INSERT INTO service.work_orders
    (work_order_id, asset_id, technician, summary, status, priority)
VALUES
    (1001, 101, 'Ada Lovelace', 'inspect', 'open', 3),
    (1002, 102, 'Grace Hopper', 'replace seal', 'scheduled', 2),
    (1003, 201, 'Katherine Johnson', 'calibrate', 'closed', 1),
    (1004, 301, 'Ada Lovelace', 'vibration review', 'open', 4);
