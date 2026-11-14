from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

# 1. Import the custom tools
from tools.market_tools import fetch_stock_price, calculate_technical_indicators, fetch_stock_news, calculate_risk_and_targets, fetch_financial_metrics
from tools.portfolio_tools import fetch_user_portfolio, calculate_smart_sip

class TradingDecision(BaseModel):
    """The strict JSON schema for the final trading output."""
    ticker: str = Field(..., description="The stock ticker symbol")
    
    # FIXED: Renamed to match the frontend JavaScript exactly
    decision_call: str = Field(..., description="Strictly output one word: BUY, SELL, or HOLD")
    
    target_price: float = Field(..., description="The exact calculated target price in the stock's native currency")
    
    # FIXED: Description updated so AI calculates stop loss correctly
    stop_loss: float = Field(..., description="The exact calculated stop loss price in the stock's native currency")
    
    # FIXED: Renamed to match the frontend JavaScript exactly
    time_period: str = Field(
        description="CRITICAL: The EXACT expected holding period in days (e.g., '14-15 Days', '5-7 Days', '30-45 Days'). Do NOT use broad terms like 'Short-Term' or 'Long-Term'. Calculate this strictly by dividing the distance to the Target Price by the stock's Average True Range (ATR) and current daily momentum."
    )
    
    technical_reasoning: str = Field(..., description="A 3-sentence explanation of the technical indicators")
    fundamental_reasoning: str = Field(..., description="A 3-sentence explanation based on news and metrics")
    
    # PERSONALIZATION FIELDS
    personalized_advice: str = Field(..., description="Address the account holder by name. Explain how this trade fits their available cash and current holdings.")
    smart_sip_recommendation: str = Field(..., description="The recommended Smart SIP amount and rationale from the SIP tool.")


@CrewBase
class ShareMarketCrew():
    """Share Market Analysis Crew"""
    
    agents_config = 'config/agents.yaml'
    tasks_config = 'config/tasks.yaml'

    @agent
    def quant_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config['quant_analyst'],
            tools=[fetch_stock_price, calculate_technical_indicators, calculate_risk_and_targets], 
            verbose=True,
            allow_delegation=False
        )

    @agent
    def fundamental_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config['fundamental_analyst'],
            tools=[fetch_stock_news, fetch_financial_metrics], 
            verbose=True,
            allow_delegation=False
        )

    @agent
    def portfolio_manager(self) -> Agent:
        return Agent(
            config=self.agents_config['portfolio_manager'],
            tools=[fetch_user_portfolio, calculate_smart_sip], # The boss now has access to the user's account
            verbose=True,
            allow_delegation=True
        )

    @task
    def technical_task(self) -> Task:
        return Task(config=self.tasks_config['technical_task'])

    @task
    def fundamental_task(self) -> Task:
        return Task(config=self.tasks_config['fundamental_task'])

    @task
    def decision_task(self) -> Task:
        return Task(
            config=self.tasks_config['decision_task'],
            output_pydantic=TradingDecision # <--- This forces the AI to output structured JSON mapping to our JS!
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents, 
            tasks=self.tasks,   
            process=Process.hierarchical,
            manager_llm=ChatOpenAI(model="gpt-4o", temperature=0.1),
            verbose=True
        )