"""
This module declares a decorator 'priv' that can be put on a command to restrict it to a particular privilege set, which
is defined by a set of users and a set of roles.
"""
import logging
from typing import Any, Awaitable, Callable, Coroutine, List, Literal, Optional, Protocol, Tuple, Union, cast

from discord import AllowedMentions, Member, User
import discord.ext.commands
import discord.utils

from bot.client import client
from bot.commands import Context, cleanup, group
import plugins
import util.db.kv
from util.discord import PartialRoleConverter, PartialUserConverter, UserError, format
from util.frozen_list import FrozenList

class PrivilegesConf(Awaitable[None], Protocol):
    def __getitem__(self, key: Tuple[str, Literal["users", "roles"]]) -> Optional[FrozenList[int]]: ...
    def __setitem__(self, key: Tuple[str, Literal["users", "roles"]],
        value: Optional[Union[List[int], FrozenList[int]]]) -> None: ...

conf: PrivilegesConf
logger: logging.Logger = logging.getLogger(__name__)

@plugins.init
async def init() -> None:
    global conf
    conf = cast(PrivilegesConf, await util.db.kv.load(__name__))

def has_privilege(priv: str, user_or_member: Union[User, Member]) -> bool:
    """Check whether a given user belongs to a given privilege set."""
    users = conf[priv, "users"]
    roles = conf[priv, "roles"]
    if users and user_or_member.id in users:
        return True
    if roles and isinstance(user_or_member, Member):
        for role in user_or_member.roles:
            if role.id in roles:
                return True
    # else we're in a DM or the user has left,
    # either way there's no roles to check
    return False

class PrivCheck:
    __slots__ = "priv"
    priv: str

    def __init__(self, priv: str):
        self.priv = priv

    def __call__(self, ctx: Context) -> bool:
        if has_privilege(self.priv, ctx.author):
            return True
        else:
            logger.warn("Denied {} to {!r}".format(ctx.invoked_with, ctx.author))
            return False

def priv(name: str) -> Callable[[Callable[..., Coroutine[Any, Any, None]]], Callable[ ..., Coroutine[Any, Any, None]]]:
    """A decorator for a command that restricts it the given privilege set."""
    return discord.ext.commands.check(PrivCheck(name))

class PrivContext(Context):
    priv: str

@cleanup
@group("priv")
@priv("shell")
async def priv_command(ctx: Context) -> None:
    """Manage privilege sets."""
    pass

def priv_exists(priv: str) -> bool:
    return conf[priv, "users"] is not None or conf[priv, "roles"] is not None

def validate_priv(priv: str) -> None:
    if not priv_exists(priv):
        raise UserError(format("Priv {!i} does not exist", priv))

@priv_command.command("new")
async def priv_new(ctx: Context, priv: str) -> None:
    """Create a new priv."""
    if priv_exists(priv):
        raise UserError(format("Priv {!i} already exists", priv))

    conf[priv, "users"] = []
    conf[priv, "roles"] = []
    await conf

    await ctx.send(format("Created priv {!i}", priv))

@priv_command.command("delete")
async def priv_delete(ctx: Context, priv: str) -> None:
    """Delete a priv."""
    validate_priv(priv)

    conf[priv, "users"] = None
    conf[priv, "roles"] = None
    await conf

    await ctx.send(format("Removed priv {!i}", priv))

@priv_command.command("show")
async def priv_show(ctx: Context, priv: str) -> None:
    """Show the users and roles in a priv."""
    validate_priv(priv)
    users = conf[priv, "users"]
    roles = conf[priv, "roles"]
    output = []
    for id in users or ():
        user = await client.fetch_user(id)
        if user is not None:
            mtext = format("{!m}({!i} {!i})", user, user.name, user.id)
        else:
            mtext = format("{!m}({!i})", id, id)
        output.append("user {}".format(mtext))
    for id in roles or ():
        role = discord.utils.find(lambda r: r.id == id, ctx.guild.roles if ctx.guild is not None else ())
        if role is not None:
            rtext = format("{!M}({!i} {!i})", role, role.name, role.id)
        else:
            rtext = format("{!M}({!i})", id, id)
        output.append("role {}".format(rtext))
    await ctx.send(format("Priv {!i} includes: {}", priv, "; ".join(output)),
        allowed_mentions=AllowedMentions.none())

@priv_command.group("add")
async def priv_add(ctx: PrivContext, priv: str) -> None:
    """Add a user or role to a priv."""
    validate_priv(priv)
    ctx.priv = priv

@priv_add.command("user")
async def priv_add_user(ctx: PrivContext, user: PartialUserConverter) -> None:
    """Add a user to a priv."""
    priv = ctx.priv
    users = conf[priv, "users"] or FrozenList()
    if user.id in users:
        raise UserError(format("User {!m} is already in priv {!i}", user.id, priv))

    conf[priv, "users"] = users + [user.id]
    await conf

    await ctx.send(format("Added user {!m} to priv {!i}", user.id, priv),
        allowed_mentions=AllowedMentions.none())

@priv_add.command("role")
async def priv_add_role(ctx: PrivContext, role: PartialRoleConverter) -> None:
    """Add a role to a priv."""
    priv = ctx.priv
    roles = conf[priv, "roles"] or FrozenList()
    if role.id in roles:
        raise UserError(format("Role {!M} is already in priv {!i}", role.id, priv))

    conf[priv, "roles"] = roles + [role.id]
    await conf

    await ctx.send(format("Added role {!M} to priv {!i}", role.id, priv),
        allowed_mentions=AllowedMentions.none())

@priv_command.group("remove")
async def priv_remove(ctx: PrivContext, priv: str) -> None:
    """Remove a user or role from a priv."""
    validate_priv(priv)
    ctx.priv = priv

@priv_remove.command("user")
async def priv_remove_user(ctx: PrivContext, user: PartialUserConverter) -> None:
    """Remove a user from a priv."""
    priv = ctx.priv
    users = conf[priv, "users"] or FrozenList()
    if user.id not in users:
        raise UserError(format("User {!m} is already not in priv {!i}", user.id, priv))

    musers = users.copy()
    musers.remove(user.id)
    conf[priv, "users"] = musers
    await conf

    await ctx.send(format("Removed user {!m} from priv {!i}", user.id, priv),
        allowed_mentions=AllowedMentions.none())

@priv_remove.command("role")
async def priv_remove_role(ctx: PrivContext, role: PartialRoleConverter) -> None:
    """Remove a role from a priv."""
    priv = ctx.priv
    roles = conf[priv, "roles"] or FrozenList()
    if role.id not in roles:
        raise UserError(format("Role {!M} is already not in priv {!i}", role.id, priv))

    mroles = roles.copy()
    mroles.remove(role.id)
    conf[priv, "roles"] = mroles
    await conf

    await ctx.send(format("Removed role {!M} from priv {!i}", role.id, priv),
        allowed_mentions=AllowedMentions.none())
