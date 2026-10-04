-- Categories Taxonomy
INSERT OR IGNORE INTO categories (id, name, parent_id, kind) VALUES
  (1, 'Income', NULL, 'income'),
  (2, 'Salary', 1, 'income'),
  (3, 'Bonus & Benefits', 1, 'income'),
  (4, 'Investment Returns', 1, 'income'),
  (5, 'Other Income', 1, 'income'),

  (10, 'Housing & Utilities', NULL, 'fixed'),
  (11, 'Mortgage', 10, 'fixed'),
  (12, 'Rent', 10, 'fixed'),
  (13, 'Electricity & Gas', 10, 'fixed'),
  (14, 'Water', 10, 'fixed'),
  (15, 'Internet & Telecom', 10, 'fixed'),
  (16, 'Municipal Taxes', 10, 'fixed'),

  (20, 'Insurance & Financial', NULL, 'fixed'),
  (21, 'Health Insurance', 20, 'fixed'),
  (22, 'Home & Liability Insurance', 20, 'fixed'),
  (23, 'Bank & Service Fees', 20, 'fixed'),

  (30, 'Subscriptions', NULL, 'fixed'),
  (31, 'Streaming & Media', 30, 'fixed'),
  (32, 'Software & Cloud', 30, 'fixed'),
  (33, 'Gym & Fitness', 30, 'fixed'),

  (40, 'Groceries & Household', NULL, 'discretionary'),
  (41, 'Supermarket', 40, 'discretionary'),
  (42, 'Pharmacy & Drugstore', 40, 'discretionary'),
  (43, 'Home & Maintenance', 40, 'discretionary'),

  (50, 'Dining & Nightlife', NULL, 'discretionary'),
  (51, 'Restaurants', 50, 'discretionary'),
  (52, 'Cafes & Bakeries', 50, 'discretionary'),
  (53, 'Bars & Nightlife', 50, 'discretionary'),
  (54, 'Food Delivery & Takeaway', 50, 'discretionary'),

  (60, 'Shopping & Personal', NULL, 'discretionary'),
  (61, 'Clothing & Shoes', 60, 'discretionary'),
  (62, 'Electronics & Gadgets', 60, 'discretionary'),
  (63, 'Personal Care', 60, 'discretionary'),
  (64, 'Gifts & Donations', 60, 'discretionary'),
  (65, 'Hobbies & Entertainment', 60, 'discretionary'),

  (70, 'Transportation', NULL, 'discretionary'),
  (71, 'Public Transit', 70, 'discretionary'),
  (72, 'Fuel', 70, 'discretionary'),
  (73, 'Parking & Tolls', 70, 'discretionary'),
  (74, 'Car Maintenance', 70, 'discretionary'),
  (75, 'Taxis & Rideshare', 70, 'discretionary'),

  (80, 'Travel & Holidays', NULL, 'discretionary'),
  (81, 'Flights', 80, 'discretionary'),
  (82, 'Lodging & Hotels', 80, 'discretionary'),
  (83, 'Vacation Activities', 80, 'discretionary'),

  (90, 'Savings & Investments', NULL, 'savings'),
  (91, 'Brokerage Deposits', 90, 'savings'),
  (92, 'Crypto Purchases', 90, 'savings'),
  (93, 'Pension Contributions', 90, 'savings'),

  (100, 'Transfers', NULL, 'transfer'),
  (101, 'Internal Transfer', 100, 'transfer'),
  (102, 'Credit Card Repayment', 100, 'transfer');

-- Default allocation profiles and targets
INSERT OR IGNORE INTO allocation_profiles (id, name, dimension, include_cash, drift_band_pct, is_active) VALUES
  (1, '80/20 Core-Satellite', 'asset_type', 0, 5.0, 1),
  (2, 'Global One-Fund', 'ticker', 0, 5.0, 0),
  (3, 'Asset Class & Cash Buffer', 'asset_class', 1, 5.0, 0);

INSERT OR IGNORE INTO allocation_targets (profile_id, bucket, target_pct) VALUES
  (1, 'etf', 80.0),
  (1, 'stock', 15.0),
  (1, 'crypto', 5.0),
  (2, 'VWCE.DE', 100.0),
  (3, 'cash', 10.0),
  (3, 'investment', 90.0);
