import json
import random
import re

from anthropic import AsyncAnthropic
from anthropic.types.beta.tools import ToolsBetaMessage

from pymedphys._ai import model_versions

from ._utilities import (
    async_cache,
    words_in_mouth_prompting,
)

SYSTEM_PROMPT = """\
You are an MSSQL SQL query result voter agent.

You are a part of a wider AI cluster that is trying to be helpful,
harmless and honest while conversing with a user.

The top level AI agent has provided the following prompt / request to
your agent cluster, of which you are fulfilling the component of
"selecting the 5 most relevant query results that have been found by the
cluster":
<sub_agent_prompt>
{sub_agent_prompt}
</sub_agent_prompt>

You are just one component of the cluster. It is NOT your job to respond
to the user, instead it is JUST your job to select the 5 most relevant
query results that might be helpful for the top level AI agent to answer
the enquiry.

You use the following xml tags to detail your chosen queries:

<selection>
<query_id>the id of the best selected best query</query_id>
<query_id>second best</query_id>

...

<query_id>fifth best</query_id>
</selection>

The transcript of the conversation thus far between the top level AI
agent and the user is the following:
<transcript>
{transcript}
</transcript>

The queries to select from are below:
<queries_and_results_to_select_from>
{shuffled_queries_and_results}
</queries_and_results_to_select_from>
"""

USER_PROMPT = """
You respond only with the best 5 queries using xml tags in the following
format:

<selection>
<query_id>the id of the selected best query</query_id>
<query_id>id of second best</query_id>

...

<query_id>id of fifth best</query_id>
</selection>
"""

START_OF_ASSISTANT_PROMPT = """
<selection>
<query_id>
"""


@async_cache
async def get_system_prompt(
    transcript: str, sub_agent_prompt: str, queries: list[str], results: list[str]
):
    query_result_pairs = list(zip(queries, results))
    random.shuffle(query_result_pairs)

    shuffled_queries_and_results = ""

    for i, (query, result) in enumerate(query_result_pairs):
        shuffled_queries_and_results += f"""\
<query id="{i}">
{query}
</query>
<result id="{i}">
{result}
</result>
"""

    return SYSTEM_PROMPT.format(
        sub_agent_prompt=sub_agent_prompt,
        transcript=transcript,
        shuffled_queries_and_results=shuffled_queries_and_results,
    )


async def get_top_k_query_ids(
    anthropic_client: AsyncAnthropic,
    messages: list[ToolsBetaMessage],
    sub_agent_prompt: str,
    queries: list[str],
    results: list[str],
) -> tuple[str, ...]:
    raw_table_names = await _get_raw_selected_table_names(
        anthropic_client=anthropic_client,
        messages=messages,
        sub_agent_prompt=sub_agent_prompt,
        queries=queries,
        results=results,
    )

    selected_query_ids = []
    for line in raw_table_names.split("\n"):
        if not line.startswith("<query_id>"):
            continue

        match = re.search(r"<query_id>(.*)</query_id>", line)
        selected_query_ids.append(int(match.group(1)))

    return selected_query_ids


async def _get_raw_selected_table_names(
    anthropic_client: AsyncAnthropic,
    messages: list[ToolsBetaMessage],
    sub_agent_prompt: str,
    queries: list[str],
    results: list[str],
) -> str:
    return await words_in_mouth_prompting(
        anthropic_client=anthropic_client,
        model=model_versions.FAST,
        system_prompt=await get_system_prompt(
            sub_agent_prompt=sub_agent_prompt,
            transcript=json.dumps(messages),
            queries=queries,
            results=results,
        ),
        appended_user_prompt=USER_PROMPT,
        start_of_assistant_prompt=START_OF_ASSISTANT_PROMPT,
    )
