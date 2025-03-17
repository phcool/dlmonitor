import arxiv
SEARCH_KEY = "cat:cs.CV+OR+cat:cs.AI+OR+cat:cs.LG+OR+cat:cs.CL+OR+cat:cs.NE+OR+cat:stat.ML"
MAX_QUERY_NUM = 10000

start=0
max_results=100
client = arxiv.Client()

# Format the search query correctly for the arxiv library
# The arxiv library uses a different format than the API URL
# Convert "cat:cs.CV+OR+cat:cs.AI" to "cat:cs.CV OR cat:cs.AI"
formatted_query = SEARCH_KEY.replace("+OR+", " OR ")

# Create search object with pagination
search_query = arxiv.Search(
    query=formatted_query,
    max_results=max_results,
    sort_by=arxiv.SortCriterion.LastUpdatedDate,
)

# Get results
results = list(client.results(search_query))

print(results)
# Convert to the same format as the original function
# processed_results = []
# for result in results:
#     paper = {
#         "arxiv_id": result.entry_id.split("/")[-1],
#         "arxiv_url": result.entry_id,
#         "pdf_url": result.pdf_url,
#         "title": result.title,
#         "summary": result.summary,
#         "authors": [author.name for author in result.authors],
#         "updated_parsed": result.updated.timetuple(),
#         "journal_reference": result.journal_ref if hasattr(result, "journal_ref") else "",
#         "tags": [{"term": category} for category in result.categories]
#     }
#     processed_results.append(paper)

# return processed_results