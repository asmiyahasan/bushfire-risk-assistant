import logging

import azure.functions as func

from collectors.bom import collect_bom_fdr
from collectors.cfa import collect_cfa
from collectors.firms import collect_firms
from collectors.vicemergency import collect_vicemergency
from collectors.dea import collect_dea

app = func.FunctionApp()

# Schedules are UTC: second minute hour day month weekday


@app.timer_trigger(schedule="0 5 */3 * * *", arg_name="timer", run_on_startup=False)
def firms_timer(timer: func.TimerRequest) -> None:
    logging.info("FIRMS result: %s", collect_firms(day_range=2))


@app.timer_trigger(schedule="0 */10 * * * *", arg_name="timer", run_on_startup=False)
def vicemergency_timer(timer: func.TimerRequest) -> None:
    logging.info("VicEmergency result: %s", collect_vicemergency())


# Every 3 hours: duplicates are skipped, so this catches each new issue.
@app.timer_trigger(schedule="0 15 */3 * * *", arg_name="timer", run_on_startup=False)
def cfa_timer(timer: func.TimerRequest) -> None:
    logging.info("CFA result: %s", collect_cfa())


@app.timer_trigger(schedule="0 20 */3 * * *", arg_name="timer", run_on_startup=False)
def bom_timer(timer: func.TimerRequest) -> None:
    logging.info("BOM result: %s", collect_bom_fdr())

@app.timer_trigger(schedule="0 25 */3 * * *", arg_name="timer", run_on_startup=False)
def dea_timer(timer: func.TimerRequest) -> None:
    logging.info("DEA result: %s", collect_dea())