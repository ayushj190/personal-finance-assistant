-- Migration: 0003_dedup_categories_and_unique_indexes.sql
-- Deduplicate categories and enforce unique constraints for root and subcategories

-- 0. Ensure referenced tables exist
CREATE TABLE IF NOT EXISTS category_budgets (
    category_id       INTEGER PRIMARY KEY REFERENCES categories(id),
    monthly_limit_eur REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS merchant_category_rules (
    merchant_normalized TEXT PRIMARY KEY,
    category_id         INTEGER NOT NULL REFERENCES categories(id),
    source              TEXT DEFAULT 'user',
    confidence          REAL DEFAULT 1.0,
    hit_count           INTEGER DEFAULT 1,
    created_at          TEXT DEFAULT (datetime('now'))
);

-- 1. Reassign child categories pointing to duplicate parents to the canonical parent
UPDATE categories
SET parent_id = (
    SELECT MIN(c2.id)
    FROM categories c2
    WHERE LOWER(c2.name) = (SELECT LOWER(c3.name) FROM categories c3 WHERE c3.id = categories.parent_id)
      AND c2.parent_id IS NULL
)
WHERE parent_id IS NOT NULL
  AND parent_id IN (
      SELECT id FROM categories WHERE id NOT IN (
          SELECT MIN(id) FROM categories GROUP BY LOWER(name), COALESCE(parent_id, -1)
      )
  );

-- 2. Reassign transactions with duplicate category IDs to canonical IDs
UPDATE transactions
SET category_id = (
    SELECT MIN(c2.id)
    FROM categories c2
    WHERE LOWER(c2.name) = (SELECT LOWER(c3.name) FROM categories c3 WHERE c3.id = transactions.category_id)
      AND COALESCE(c2.parent_id, -1) = (SELECT COALESCE(c3.parent_id, -1) FROM categories c3 WHERE c3.id = transactions.category_id)
)
WHERE category_id IS NOT NULL
  AND category_id IN (
      SELECT id FROM categories WHERE id NOT IN (
          SELECT MIN(id) FROM categories GROUP BY LOWER(name), COALESCE(parent_id, -1)
      )
  );

-- 3. Reassign merchant rules
UPDATE merchant_category_rules
SET category_id = (
    SELECT MIN(c2.id)
    FROM categories c2
    WHERE LOWER(c2.name) = (SELECT LOWER(c3.name) FROM categories c3 WHERE c3.id = merchant_category_rules.category_id)
      AND COALESCE(c2.parent_id, -1) = (SELECT COALESCE(c3.parent_id, -1) FROM categories c3 WHERE c3.id = merchant_category_rules.category_id)
)
WHERE category_id IN (
    SELECT id FROM categories WHERE id NOT IN (
        SELECT MIN(id) FROM categories GROUP BY LOWER(name), COALESCE(parent_id, -1)
    )
);

-- 4. Delete orphan duplicate budgets
DELETE FROM category_budgets
WHERE category_id IN (
    SELECT id FROM categories WHERE id NOT IN (
        SELECT MIN(id) FROM categories GROUP BY LOWER(name), COALESCE(parent_id, -1)
    )
);

-- 5. Delete duplicate categories
DELETE FROM categories
WHERE id NOT IN (
    SELECT MIN(id) FROM categories GROUP BY LOWER(name), COALESCE(parent_id, -1)
);

-- 6. Prevent future duplicates via unique partial indexes
CREATE UNIQUE INDEX IF NOT EXISTS idx_cat_unique_parent_null
ON categories (LOWER(name)) WHERE parent_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_cat_unique_with_parent
ON categories (LOWER(name), parent_id) WHERE parent_id IS NOT NULL;
