from mcp.server.fastmcp import FastMCP

mcp = FastMCP("FinanceNavigatorMCP")

@mcp.tool()
def fetch_transactions() -> list:
    """Fetch the list of recent transactions for the user.
    
    Returns:
        list: A list of dicts representing transactions.
    """
    return [
        {"description": "Landlord Rent Payment", "amount": 1200.0, "category": "Housing"},
        {"description": "Whole Foods Grocery", "amount": 150.0, "category": "Food"},
        {"description": "Netflix Subscription", "amount": 15.99, "category": "Entertainment"},
        {"description": "Electric Utility Bill", "amount": 85.50, "category": "Utilities"},
        {"description": "Luxury Spa Treatment", "amount": 550.0, "category": "Entertainment"}
    ]

@mcp.tool()
def fetch_budgets() -> dict:
    """Fetch the budget limits per category for the user.
    
    Returns:
        dict: A mapping of category names to budget limit amounts.
    """
    return {
        "Housing": 1500.0,
        "Food": 400.0,
        "Utilities": 200.0,
        "Entertainment": 300.0,
        "Savings": 500.0
    }

@mcp.tool()
def fetch_savings_goals() -> dict:
    """Fetch the savings goals for the user.
    
    Returns:
        dict: A mapping of savings goal names to goal amounts.
    """
    return {
        "emergency_fund": 5000.0,
        "vacation": 2000.0
    }

@mcp.tool()
def save_categorized_transactions(transactions: list) -> str:
    """Save the list of categorized transactions to the financial system.
    
    Args:
        transactions: A list of transactions with category assigned.
        
    Returns:
        str: A message indicating success or failure.
    """
    return f"Successfully saved {len(transactions)} categorized transactions to the ledger."

if __name__ == "__main__":
    mcp.run(transport="stdio")
