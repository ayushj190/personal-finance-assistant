# Privacy Policy

**Effective Date:** October 4, 2026  
**Application:** Personal Finance Assistant  
**Contact / Data Protection Email:** ayush@joshi.contact  

## 1. Overview
Personal Finance Assistant is a self-hosted, personal finance management tool running locally on your own machine. We respect your privacy and process financial data strictly to provide you with insights into your own finances.

## 2. Data We Process
When you connect your bank account via Open Banking (Enable Banking AISP), the application accesses:
- **Account details:** Account identifier, IBAN, account name, currency.
- **Balances:** Current and available account balances.
- **Transactions:** Transaction dates, descriptions, counterparties, and amounts.

## 3. Where Data is Stored
- **100% Local Storage:** All account data, transactions, categories, and authentication tokens are stored exclusively on your local machine in an encrypted SQLite database and encrypted local secrets vault.
- **No Third-Party Analytics:** We do not sell, share, or transmit your financial data to third-party advertisers, brokers, or external servers.

## 4. Third-Party Services
- **Enable Banking Oy:** Used as an authorized Account Information Service Provider (AISP) to securely connect to European PSD2 banking APIs under your explicit consent. Your consent can be revoked at any time.
- **Brave Search API (Optional):** If configured in settings, public merchant names are queried against Brave Search to improve automated transaction categorization. No amounts, IBANs, or transaction balances are ever sent.

## 5. User Rights (GDPR)
Under EU GDPR:
- You have full access to your data at any time (stored locally).
- You can delete your data completely by clearing your local application data directory.
- You can revoke bank consent at any time via your bank's portal or by removing the connection in application settings.

For questions, contact: `ayush@joshi.contact`.
