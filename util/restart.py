import sys
import os
import atexit
import discord_client
import asyncio
import logging

will_restart = False

logger = logging.getLogger(__name__)

@atexit.register
def atexit_restart_maybe():
    if will_restart:
        logger.info("Re-executing {!r} {!r}".format(sys.interpreter, sys.argv))
        try:
            os.execv(sys.interpreter, sys.argv)
        except:
            logger.critical("Restart failed", exc_info=True)

def restart():
    logger.info("Restart requested", stack_info=True)
    will_restart = True
    if not discord_client.client.is_closed():
        discord_client.client.close()
    asyncio.get_event_loop().stop()
