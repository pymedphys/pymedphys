# Create an agent that searches through the query results and
# deduplicates the information provided to the top level AI agent.

# Only vote on the best query/result pairs after they have first been
# deduplicated.

# That way instead of providing multiple queries all saying the same
# thing to the top level agent (resulting in the agent being overly
# confident) the top level agent will get a good overview of the data
# being observed.
