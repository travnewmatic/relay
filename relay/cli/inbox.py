import click

from urllib.parse import urlparse

from . import cli, pass_state

from ..database.schema import Instance
from ..misc import ACTOR_FORMATS, Message
from ..state import State


@cli.group("inbox")
def cli_inbox() -> None:
	"Manage the inboxes in the database"


@cli_inbox.command("list")
@pass_state
def cli_inbox_list(state: State) -> None:
	"List the connected instances or relays"

	click.echo("Connected to the following instances or relays:")

	with state.database.session() as conn:
		for row in conn.get_inboxes():
			click.echo(f"- {row.inbox}")


@cli_inbox.command("follow")
@click.argument("actor")
@pass_state
async def cli_inbox_follow(state: State, actor: str) -> None:
	"Follow an actor (Relay must be running)"

	instance: Instance | None = None

	async with state.client:
		with state.database.session() as conn:
			if conn.get_domain_ban(actor):
				click.echo(f"Error: Refusing to follow banned actor: {actor}")
				return

			if (instance := conn.get_inbox(actor)) is not None:
				inbox = instance.inbox

			else:
				if not actor.startswith("http"):
					actor = f"https://{actor}/actor"

				actor_data = await state.client.get(actor, cls = Message, sign_headers = True)

				if not actor_data:
					click.echo(f"Failed to fetch actor: {actor}")
					return

				try:
					inbox = actor_data.shared_inbox
				except (KeyError, TypeError):
					inbox = actor_data["inbox"]

		message = Message.new_follow(
			host = state.config.domain,
			actor = actor
		)

		await state.client.post(inbox, message, instance)
		click.echo(f"Sent follow message to actor: {actor}")


@cli_inbox.command("unfollow")
@click.argument("actor")
@pass_state
async def cli_inbox_unfollow(state: State, actor: str) -> None:
	"Unfollow an actor (Relay must be running)"

	instance: Instance | None = None

	async with state.client:
		with state.database.session() as conn:
			if conn.get_domain_ban(actor):
				click.echo(f"Error: Refusing to follow banned actor: {actor}")
				return

			if (instance := conn.get_inbox(actor)):
				inbox = instance.inbox
				message = Message.new_unfollow(
					host = state.config.domain,
					actor = actor,
					follow = instance.followid
				)

			else:
				if not actor.startswith("http"):
					actor = f"https://{actor}/actor"

				actor_data = await state.client.get(actor, cls = Message, sign_headers = True)

				if not actor_data:
					click.echo("Failed to fetch actor")
					return

				try:
					inbox = actor_data.shared_inbox
				except (KeyError, TypeError):
					inbox = actor_data["inbox"]
				message = Message.new_unfollow(
					host = state.config.domain,
					actor = actor,
					follow = {
						"type": "Follow",
						"object": actor,
						"actor": f"https://{state.config.domain}/actor"
					}
				)

		await state.client.post(inbox, message, instance)
		click.echo(f"Sent unfollow message to: {actor}")


@cli_inbox.command("add")
@click.argument("inbox")
@click.option("--actor", "-a", help = "Actor url for the inbox")
@click.option("--followid", "-f", help = "Url for the follow activity")
@click.option("--software", "-s", help = "Nodeinfo software name of the instance")
@pass_state
async def cli_inbox_add(
				state: State,
				inbox: str,
				actor: str | None = None,
				followid: str | None = None,
				software: str | None = None) -> None:
	"Add an inbox to the database"

	if not inbox.startswith("http"):
		domain = inbox
		inbox = f"https://{inbox}/inbox"

	else:
		domain = urlparse(inbox).netloc

	if not software:
		async with state.client:
			if (nodeinfo := await state.client.fetch_nodeinfo(domain)):
				software = nodeinfo.sw_name

	if not actor and software:
		try:
			actor = ACTOR_FORMATS[software].format(domain = domain)

		except KeyError:
			pass

	with state.database.session() as conn:
		if conn.get_domain_ban(domain):
			click.echo(f"Refusing to add banned inbox: {inbox}")
			return

		if conn.get_inbox(inbox):
			click.echo(f"Error: Inbox already in database: {inbox}")
			return

		conn.put_inbox(domain, inbox, actor, followid, software)

	click.echo(f"Added inbox to the database: {inbox}")


@cli_inbox.command("remove")
@click.argument("inbox")
@pass_state
def cli_inbox_remove(state: State, inbox: str) -> None:
	"Remove an inbox from the database"

	with state.database.session() as conn:
		if not conn.del_inbox(inbox):
			click.echo(f"Inbox not in database: {inbox}")
			return

	click.echo(f"Removed inbox from the database: {inbox}")
