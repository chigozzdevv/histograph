# Dataset provenance

Histograph's reference environment uses:

> Azamuke, Denish (2024), Synthetic Mobile Money Transaction Dataset, Mendeley Data, V2,
> doi:10.17632/zhj366m53p.2

- Source: <https://data.mendeley.com/datasets/zhj366m53p/2>
- File: `synthetic_mobile_money_transaction_dataset.csv`
- Version: 2
- DOI: <https://doi.org/10.17632/zhj366m53p.2>
- License: [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/)

The raw source and generated Parquet are not tracked in Git. `prepare-data` creates a manifest with
the source citation, resolved column mapping, row counts, prevalence, feature definitions, and
SHA-256 hashes of the raw and prepared files.

The source is synthetic and is used only to make Histograph's reliability scenarios reproducible.
Do not interpret its prevalence or behavior as representative of a deployed mobile-money network.
