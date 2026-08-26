CREATE TABLE returns (
    return_id INTEGER,
    sale_id INTEGER,
    reason VARCHAR,
    return_date DATE
);

INSERT INTO returns VALUES
    (1, 2, 'Damaged in transit', '2025-01-20'),
    (2, 6, 'Wrong item', '2025-02-18');
