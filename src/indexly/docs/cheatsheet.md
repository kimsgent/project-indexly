## **1️⃣ Sample Files**

### **JSON (`sale.json`)**

```json
{
  "records": [
    {"id": 1, "product": "Widget", "quantity": 10, "price": 2.5},
    {"id": 2, "product": "Gadget", "quantity": 5, "price": 3.0}
  ]
}
```

---

### **CSV (`data.csv`)**

```csv
id,product,quantity,price
1,Widget,10,2.5
2,Gadget,5,3.0
```

---

### **YAML (`config.yaml`)**

```yaml
settings:
  version: 1.0
  debug: true
  threshold: 0.75
```

---

### **XML (`orders.xml`)**

```xml
<orders>
    <order>
        <id>1</id>
        <product>Widget</product>
        <quantity>10</quantity>
        <price>2.5</price>
    </order>
    <order>
        <id>2</id>
        <product>Gadget</product>
        <quantity>5</quantity>
        <price>3.0</price>
    </order>
</orders>
```

---

### **Excel (`financials.xlsx`)**

| ID | Product | Quantity | Price |
| -- | ------- | -------- | ----- |
| 1  | Widget  | 10       | 2.5   |
| 2  | Gadget  | 5        | 3.0   |

> Save as `.xlsx` using Excel or `pandas.to_excel()`.

---

### **Parquet (`parquet_data.parquet`)**

> You can convert the CSV above to Parquet using pandas:

```python
import pandas as pd
df = pd.read_csv("data.csv")
df.to_parquet("parquet_data.parquet")
```

---

### **SQLite (`my_database.db`)**

> Minimal example: table `sales` with same CSV data:

```sql
CREATE TABLE sales (
    id INTEGER PRIMARY KEY,
    product TEXT,
    quantity INTEGER,
    price REAL
);

INSERT INTO sales VALUES (1, 'Widget', 10, 2.5);
INSERT INTO sales VALUES (2, 'Gadget', 5, 3.0);
```

> Or create via Python:

```python
import sqlite3
import pandas as pd

df = pd.read_csv("data.csv")
conn = sqlite3.connect("my_database.db")
df.to_sql("sales", conn, index=False, if_exists="replace")
conn.close()
```

---

## **2️⃣ CLI Test Commands Cheat Sheet**

### **Universal loader / analyze-file**

```bash
indexly analyze-file sale.json --show-summary
indexly analyze-file data.csv --auto-clean --normalize --show-summary
indexly analyze-file financials.xlsx --show-summary
indexly analyze-file parquet_data.parquet --show-summary
indexly analyze-file config.yaml --show-summary
indexly analyze-file orders.xml --show-summary
indexly analyze-file my_database.db --show-summary
```

---

### **Direct CSV analysis**

```bash
indexly analyze-csv data.csv --auto-clean --normalize --remove-outliers --show-summary --show-chart ascii --chart-type hist
```

---

### **Direct JSON analysis**

```bash
indexly analyze-json sale.json --show-summary --show-chart --chunk-size 5000
```

---

### **Export results**

```bash
indexly analyze-file sale.json --show-summary --export-path analysis.md --format md
indexly analyze-csv data.csv --auto-clean --export-cleaned cleaned_data.csv --export-format csv
```

---

### **Timeseries / Visualization (CSV)**

```bash
indexly analyze-file data.csv --timeseries --x date --y quantity,price --freq D --agg sum --rolling 2 --mode interactive
```

---

### **.gz variants**

```bash
# Compress JSON
gzip sale.json
indexly analyze-file sale.json.gz --show-summary

# Compress CSV
gzip data.csv
indexly analyze-file data.csv.gz --auto-clean --show-summary
```