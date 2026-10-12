# Verification Plan: Multi Bank Manual Accounts and Hybrid Statement Ingestion

Verify each acceptance criterion before closing Slice 12:

- [ ] Open Settings or Import Files -> click Add Manual Account -> verify modal dialog opens with Name, Institution, Asset Class, Currency, and Initial Balance -> AC-1
- [ ] Create a manual account with an initial balance -> verify account is created in `accounts` and starting snapshot is recorded in `account_snapshots` with exact minor units -> AC-2
- [ ] Upload sample Türkiye İş Bankası PDF statements (both Turkish and English headers) -> verify `parse_isbank_pdf` extracts transactions, dates, and amounts without error -> AC-3
- [ ] Upload an unformatted or generic PDF statement -> verify fallback to local Ollama (`generate_json`) successfully parses transactions -> AC-4
- [ ] In Import Files UI -> verify candidate account is detected from statement, and verify target account selectbox allows selecting or changing target account -> AC-5
- [ ] Import transactions with non EUR currency (such as TRY) -> verify `amount_minor` and `currency` are stored in native currency without forced FX scaling -> AC-6
- [ ] Verify detected statement ending balance displays in the UI and updates the account snapshot upon confirmation -> AC-7
- [ ] Run test suite -> verify all unit tests pass -> AC-1 through AC-7
