from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.api.test_routes import generate_structured_plan, PlanRequest
from app.integrations.calendar_integration import push_plan_to_gcal, get_tokens
from app.config import get_settings
import logging
import asyncio

logger = logging.getLogger(__name__)

async def automated_planner_job():
    """Background job that generates a plan and pushes it to Google Calendar."""
    logger.info("Running automated weekly planner job...")
    
    # We need a user ID since our token store uses user_ids. 
    # For now, we assume there's a primary user "founder-primary"
    user_id = "founder-primary" 
    
    # Check if user has authenticated, if not skip the automation
    if not get_tokens(user_id):
        logger.warning(f"Skipping automation: No Google Calendar tokens found for {user_id}. Please authenticate via /api/test/plan/gcal/auth first.")
        return

    settings = get_settings()

    try:
        # 1. Generate the plan (using mock_plan to save API keys)
        logger.info("Generating weekly plan...")
        request = PlanRequest(message="mock_plan")
        plan_response = await generate_structured_plan(request)
        
        # The plan is now in _latest_plan globally.
        # 2. Push to Google Calendar
        from app.agents.planner_models import WeeklyPlan
        from app.api.test_routes import _latest_plan
        
        if not _latest_plan:
             logger.error("No plan was generated to push.")
             return
             
        plan = WeeklyPlan.model_validate(_latest_plan)
        
        logger.info("Pushing plan to Google Calendar...")
        result = await push_plan_to_gcal(
            plan=plan,
            user_id=user_id,
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
        )
        
        logger.info(f"Automated planner finished! Created {result['events_created']} events.")
        
    except Exception as e:
        logger.error(f"Automated planner failed: {e}")

def start_scheduler():
    scheduler = AsyncIOScheduler()
    
    # Run the planner every Monday at 8:00 AM
    # For testing, we can run it every minute
    scheduler.add_job(automated_planner_job, 'cron', day_of_week='mon', hour=8, minute=0)
    
    # Add a testing job that runs 30 seconds after startup
    import datetime
    run_date = datetime.datetime.now() + datetime.timedelta(seconds=30)
    scheduler.add_job(automated_planner_job, 'date', run_date=run_date)
    
    scheduler.start()
    logger.info("Background planner scheduler started.")
