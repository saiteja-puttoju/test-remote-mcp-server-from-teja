from fastmcp import FastMCP

mcp = FastMCP(name="example_mcp")

@mcp.tool
def add_numbers(a: float, b: float) -> float:
    """Add two numbers together."""
    return a + b

@mcp.tool
def subtract_numbers(a: float, b: float) -> float:
    """Subtract two numbers."""
    return a - b

@mcp.tool
def multipy_numbers(a: float, b:float) -> float:
    """Muliply two numbers."""
    return a * b


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)