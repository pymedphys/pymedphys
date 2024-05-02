import json
import random
import re

from anthropic import AsyncAnthropic
from anthropic.types.beta.tools import ToolsBetaMessage

from pymedphys._ai import model_versions

from ._utilities import (
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

<final_selection>
<query_id>the id of the best selected best query</query_id>
<query_id>second best</query_id>

...

<query_id>fifth best</query_id>
</final_selection>

Prior to making your final selection you go through the following steps:

1. Think through your answer inside <thinking> tags
2. Provide drafts of your selection inside <draft_selection> tags
3. Undergo reflection and critique on your draft selection inside
   <reflection> tags
4. Provide a score between 0 and 10 within <selection_score> tags for
   how well the queries within the <draft_selection> meet the
   requirements.
4. Repeat steps 2, 3, and 4 multiple times until both at least 3 repeats
   have been undergone as well as a selection_score of at least 8 has
   been achieved.
5. Provide your final selection within <final_selection> tags.
6. Finished

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

<final_selection>
<query_id>the id of the best selected best query</query_id>
<query_id>second best</query_id>

...

<query_id>fifth best</query_id>
</final_selection>

Prior to making your final selection you go through the following steps:

1. Think through your answer inside <thinking> tags
2. Provide drafts of your selection inside <draft_selection> tags
3. Undergo reflection and critique on your draft selection inside
   <reflection> tags
4. Provide a score between 0 and 10 within <selection_score> tags for
   how well the queries within the <draft_selection> meet the
   requirements.
4. Repeat steps 2, 3, and 4 multiple times until both at least 3 repeats
   have been undergone as well as a selection_score of at least 8 has
   been achieved.
5. Provide your final selection within <final_selection> tags.
6. Finished
"""

START_OF_ASSISTANT_PROMPT = """
<thinking>
"""


async def get_system_prompt(
    transcript: str, sub_agent_prompt: str, query_result_pairs: list[tuple[str, str]]
):
    queries_and_results_prompt = ""

    for i, (query, result) in enumerate(query_result_pairs):
        queries_and_results_prompt += f"""\
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
        shuffled_queries_and_results=queries_and_results_prompt,
    )


async def get_top_k_query_ids(
    anthropic_client: AsyncAnthropic,
    messages: list[ToolsBetaMessage],
    sub_agent_prompt: str,
    query_result_pairs: list[tuple[str, str]],
) -> tuple[str, ...]:
    shuffled_index = list(range(len(query_result_pairs)))
    random.shuffle(shuffled_index)

    shuffled_query_result_pairs = [query_result_pairs[i] for i in shuffled_index]

    raw_selected_shuffled_indices = await _get_raw_top_k_query_ids(
        anthropic_client=anthropic_client,
        messages=messages,
        sub_agent_prompt=sub_agent_prompt,
        query_result_pairs=shuffled_query_result_pairs,
    )

    post_final_selection = raw_selected_shuffled_indices.split("<final_selection>")[1]

    selected_shuffled_query_ids = []
    for line in post_final_selection.split("\n"):
        if not line.startswith("<query_id>"):
            continue

        match = re.search(r"<query_id>(.*)</query_id>", line)
        selected_shuffled_query_ids.append(int(match.group(1)))

    unshuffled_query_ids = [shuffled_index[i] for i in selected_shuffled_query_ids]

    return unshuffled_query_ids


async def _get_raw_top_k_query_ids(
    anthropic_client: AsyncAnthropic,
    messages: list[ToolsBetaMessage],
    sub_agent_prompt: str,
    query_result_pairs: list[tuple[str, str]],
) -> str:
    return await words_in_mouth_prompting(
        anthropic_client=anthropic_client,
        model=model_versions.FAST,
        system_prompt=await get_system_prompt(
            sub_agent_prompt=sub_agent_prompt,
            transcript=json.dumps(messages),
            query_result_pairs=query_result_pairs,
        ),
        appended_user_prompt=USER_PROMPT,
        start_of_assistant_prompt=START_OF_ASSISTANT_PROMPT,
    )
