
## 2026-10-31 - [Optimize String Search in Pandas DataFrames]
**Learning:** Using `df.apply(func, axis=1)` for text search across multiple columns is significantly slower (~10x) than using a vectorized approach or a Python list comprehension with `zip()`. In Streamlit applications, this blocking synchronous operation on the main thread causes UI unresponsiveness during keystrokes.
**Action:** Always prefer vectorized string operations (like `df['col'].str.contains()`) or list comprehensions over `df.apply(..., axis=1)` when filtering rows based on string conditions across multiple columns.
