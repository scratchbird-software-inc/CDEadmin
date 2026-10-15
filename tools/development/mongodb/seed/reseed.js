// Idempotent sample data: customers and sales for CDEadmin MongoDB demos.
// Run inside the container: mongosh cdeadmin_demo /seed/reseed.js

const database = db.getSiblingDB('cdeadmin_demo');

const customers = [
  {
    _id: 1,
    name: 'Northwind Field Lab',
    city: 'Toronto',
    region: 'ON',
    email: 'contact@northwind.example',
    tier: 'enterprise',
  },
  {
    _id: 2,
    name: 'Contoso Water',
    city: 'Hamilton',
    region: 'ON',
    email: 'billing@contoso-water.example',
    tier: 'professional',
  },
  {
    _id: 3,
    name: 'Adventure Works Mining',
    city: 'Sudbury',
    region: 'ON',
    email: 'procurement@adventure-works.example',
    tier: 'enterprise',
  },
];

const sales = [
  {
    _id: 5001,
    customer_id: 1,
    product: 'Pump maintenance kit',
    quantity: 2,
    unit_price: 124.995,
    amount: 249.99,
    currency: 'CAD',
    sold_at: ISODate('2025-03-15T14:30:00Z'),
    status: 'completed',
  },
  {
    _id: 5002,
    customer_id: 1,
    product: 'Annual field-service contract',
    quantity: 1,
    unit_price: 4800,
    amount: 4800,
    currency: 'CAD',
    sold_at: ISODate('2025-01-10T09:00:00Z'),
    status: 'completed',
  },
  {
    _id: 5003,
    customer_id: 2,
    product: 'Flow meter calibration',
    quantity: 1,
    unit_price: 675.5,
    amount: 675.5,
    currency: 'CAD',
    sold_at: ISODate('2025-04-02T16:45:00Z'),
    status: 'completed',
  },
  {
    _id: 5004,
    customer_id: 2,
    product: 'Control valve assembly',
    quantity: 3,
    unit_price: 890,
    amount: 2670,
    currency: 'CAD',
    sold_at: ISODate('2025-05-18T11:20:00Z'),
    status: 'pending',
  },
  {
    _id: 5005,
    customer_id: 3,
    product: 'Ventilation fan upgrade',
    quantity: 4,
    unit_price: 1525,
    amount: 6100,
    currency: 'CAD',
    sold_at: ISODate('2025-02-28T08:15:00Z'),
    status: 'completed',
  },
  {
    _id: 5006,
    customer_id: 3,
    product: 'Vibration monitoring sensors',
    quantity: 12,
    unit_price: 185.25,
    amount: 2223,
    currency: 'CAD',
    sold_at: ISODate('2025-06-01T13:00:00Z'),
    status: 'shipped',
  },
];

database.customers.deleteMany({});
database.sales.deleteMany({});
database.customers.insertMany(customers);
database.sales.insertMany(sales);

database.customers.createIndex({ name: 1 }, { name: 'customer_name' });
database.customers.createIndex({ region: 1, city: 1 }, { name: 'region_city' });
database.sales.createIndex({ customer_id: 1, sold_at: -1 }, { name: 'customer_sold_at' });
database.sales.createIndex({ status: 1 }, { name: 'sale_status' });

printjson({
  database: database.getName(),
  customers: database.customers.countDocuments(),
  sales: database.sales.countDocuments(),
  revenue_completed_cad: database.sales.aggregate([
    { $match: { status: 'completed' } },
    { $group: { _id: null, total: { $sum: '$amount' } } },
  ]).toArray(),
});
