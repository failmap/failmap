import logging
from typing import List

from websecmap.scanners.models import Product, ProductGoal, ProductHierarchy, ProductRelationship, ProductVendor

log = logging.getLogger(__name__)


def enrich_product_metadata():
    log.info("Enrichting Product Metadata")
    # llm_hello()

    for product in Product.objects.all():
        enrich_product(product)

    # llm_thank_you()


def enrich_product(product: Product):
    enrich_product_vendor(product)
    enrich_product_goal(product)
    enrich_product_arbitrary_json_data(product)
    enrich_product_programming_language(product)
    enrich_possible_operating_systems(product)
    enrich_product_execution_environment(product)
    enrich_product_intended_use_case(product)
    enrich_product_tag_cloud(product)
    enrich_product_is_open_source(product)

    # llm4 can create something like this
    # enrich_product_contextual_graph(product)


def clear_enrichment():
    for product in Product.objects.all():
        product.vendor = None
        product.goal = None
        product.arbitrary_json_data = None
        product.save()
        log.debug("Cleared enrichment for product %s", product.name)


def enrich_product_arbitrary_json_data(product: Product):
    # these are the system requirements that are extracted from llm...
    if product.arbitrary_json_data:
        return
    product.arbitrary_json_data = llm_get_product_system_requirements(product.verbose_name)
    product.save()
    log.debug("Enriched product %s with data %s", product.verbose_name, product.arbitrary_json_data)


def enrich_product_vendor(product: Product):
    if product.vendor:
        return

    vendor = llm_get_product_vendor(product.name)
    if semantically_empty(vendor):
        return

    vendor, _ = ProductVendor.objects.get_or_create(name=vendor[:200])
    product.vendor = vendor
    product.save()
    log.debug("Enriched product %s with vendor %s", product.name, product.vendor.name)


def enrich_product_goal(product: Product):
    if product.goal:
        return

    goal = llm_get_product_goal(product.verbose_name)
    if semantically_empty(goal):
        return

    goal, _ = ProductGoal.objects.get_or_create(name=goal[:200])
    product.goal = goal
    product.save()
    log.debug("Enriched product %s with goal %s", product.verbose_name, product.goal.name)


def enrich_product_programming_language(product: Product):
    relationship, _ = ProductRelationship.objects.get_or_create(name="written in")
    if ProductHierarchy.objects.filter(product=product, relationship=relationship).exists():
        return

    # don't service unknown unknowns :)
    if product.verbose_name == "Unknown Unknown":
        return

    programming_language = llm_get_product_programming_language(product.verbose_name)
    if semantically_empty(programming_language):
        programming_language_product, _ = Product.objects.get_or_create(name="Unknown")
        ProductHierarchy.objects.get_or_create(
            product=product, related_product=programming_language_product, relationship=relationship
        )
        return

    programming_language_product, _ = Product.objects.get_or_create(name=programming_language[:200])
    ProductHierarchy.objects.get_or_create(
        product=product, related_product=programming_language_product, relationship=relationship
    )
    log.debug("Enriched product %s with data %s", product.verbose_name, product.arbitrary_json_data)


def enrich_product_execution_environment(product: Product):
    if not product.common_execution_environment:
        response = llm_get_product_common_execution_environment(product.verbose_name)
        if semantically_empty(response):
            product.common_execution_environment = "Unknown"
        else:
            product.common_execution_environment = response
        product.save()


def enrich_product_intended_use_case(product: Product):
    if not product.intended_use_case_description:
        product.intended_use_case_description = llm_get_product_intended_use_case_description(product.verbose_name)
        product.save()


def enrich_product_contextual_graph(product: Product):
    if not product.contextual_graph:
        product.contextual_graph = llm_get_product_contextual_graph(product.verbose_name)
        product.save()


def enrich_product_is_open_source(product: Product):
    if product.is_open_source not in [True, False]:
        product.is_open_source = llm_get_product_is_open_source(product.verbose_name)
        product.save()


def enrich_product_tag_cloud(product: Product):
    if product.tags.all().count() == 0:
        tags = llm_get_product_tag_cloud(product.verbose_name)
        for tag in tags:
            log.debug("Enriched product %s with tag %s", product.verbose_name, tag)
            product.tags.add(tag.strip())


def enrich_possible_operating_systems(product: Product):
    # this information is useless, basically everything runs on everything on the web, so who cares.
    return
    # operating_systems = ["Windows", "Linux", "MacOS", "Mac OS", "Unix"]
    # # do not find the relationship again after one round of checking. It will be at least one of these.
    # relationship, _ = ProductRelationship.objects.get_or_create(name="runs on operating system")
    # if ProductHierarchy.objects.filter(product=product, relationship=relationship).exists():
    #     return
    # for operating_system in operating_systems:
    #     if operating_system.lower() not in product.arbitrary_json_data.lower():
    #         continue
    #     # correct spelling:
    #     if operating_system in ["mac os", "macos"]:
    #         operating_system = "MacOS"
    #     operating_sytem_product, _ = Product.objects.get_or_create(name=operating_system)
    #     ProductHierarchy.objects.get_or_create(product=product, related_product=operating_sytem_product,
    #                                            relationship=relationship)
    #     log.debug("Enriched product %s with data %s", product.verbose_name, product.arbitrary_json_data)
    # Most web software runs on all operating systems. So here is also not too much to add.


def enrich_used_databases(product: Product):
    # does it use a database?
    # Yes or no: does the software product "Django Web Framework" support data storage inside a database?
    # In one word: does the software product "OpenSSL" support data storage inside a database?
    # # yes ...
    # # no ...
    # As a json list response: what are the primarily targetted brands of databases the software product
    # "VMWare Horizon" supports?
    # Most software supports most databases one way or the other. This is not really valuable now.
    ...


# Working with responses wher llm has no answer
def semantically_empty(text: str) -> bool:
    if text is None:
        return True

    text = text.lower().strip()
    if text in {"unknown", "none", ""}:
        return True

    # As an AI language model, I cannot access specific information on
    if "as an AI language model" in text:
        return True

    if "as a language model" in text:
        return True

    if "I cannot" in text:
        return True

    return False


# Abstraction of questions
def ask_question(question, expected_output: str = None):
    raise NotImplementedError(
        "Support for OpenAI has been dropped as there is no guarantee that the content it dreams of "
        "is copyright free. This code and structure are still in place to support another model "
        "in the future. - Even though product descriptions are usually marketing material, there is no guarantee."
    )


def example_llm_api_implementation(question, expected_output: str = None) -> str:
    """
    Typical OpenAi response objects:
    {
    'id': 'chatcmpl-6p9XYPYSTTRi0xEviKjjilqrWU2Ve',
    'object': 'chat.completion',
    'created': 1677649420,
    'model': 'gpt-3.5-turbo',
    'usage': {'prompt_tokens': 56, 'completion_tokens': 31, 'total_tokens': 87},
    'choices': [
      {
       'message': {
         'role': 'assistant',
         'content': 'The 2020 World Series was played in Arlington, Texas at the Globe Life Field,
         which was the new home stadium for the Texas Rangers.'},
       'finish_reason': 'stop',
       'index': 0
      }
     ]
    }
    """

    # This implementation was for openai. Each library has a different approach. This is left here for inspiration.

    # log.debug("> WebSecMap: %s", question)
    # large_language_model.api_key = constance_cached_value("LARGE_LANGUAGE_MODEL_NAME_API_KEY")
    # messages = [
    #     {"role": "user", "content": question},
    # ]
    # if expected_output == "csv":
    #     messages.append(
    #         {"role": "assistant", "content": "You are an assistant who only speaks CSV. Do not write normal text."}
    #     )

    # completion = large_language_model.ChatCompletion.create(
    #   model=constance_cached_value("LARGE_LANGUAGE_MODEL_MODEL_NAME"), messages=messages)

    # answer = completion.choices[0].message["content"]
    # if answer.endswith("."):
    #     answer = answer[:-1]

    # log.debug("< llm: %s", answer.strip())

    # return answer.strip()


# Interaction with llm:
def llm_get_product_goal(product_name: str) -> str:
    return ask_question(f"In one word, what is the goal of the software product {product_name}?")


def llm_get_product_vendor(product_name: str) -> str:
    return ask_question(f"In one word: The software product {product_name} is created by which company? ")


def llm_get_product_system_requirements(product_name: str) -> str:
    return ask_question(f"Summarized in JSON format, what are the system requirements for {product_name}?")


def llm_get_product_programming_language(product_name: str) -> str:
    return ask_question(
        f"In a single word, what is the programming language "
        f"that software product {product_name} is written in and/or depends on? "
        f"Please give the shortest answer possible."
    )


def llm_get_product_common_execution_environment(product_name: str) -> str:
    answer = ask_question(
        f"Please answer with Browser, Server, and nothing else to the following question: "
        f"does {product_name} run in the Browser or on the Server?"
    )

    answer = answer.lower().strip()
    if "browser" in answer:
        return "Browser"

    if "server" in answer:
        return "Server"

    return "Unknown"


def llm_get_product_is_open_source(product_name: str) -> bool:
    answer = ask_question(f"Yes, No or Unkown: Is the software product {product_name} open source?")
    answer = answer.lower()
    return "yes" in answer


def llm_get_product_tag_cloud(product_name: str) -> List[str]:
    answer = ask_question(
        f'Can you make a comma separated tag list for for software product "{product_name}".', expected_output="csv"
    )
    return answer.replace('"', "").lower().split(",")


def llm_get_product_intended_use_case_description(product_name: str) -> str:
    return ask_question(
        f"Summarized in under 400 characters, what is the intended use case " f'of software product "{product_name}"?'
    )


def llm_get_product_contextual_graph(product_name: str) -> str:
    return ask_question(
        f"Can you create a ascii contextual graph of the " f'application of software product "{product_name}"?'
    )


def llm_hello() -> str:
    return ask_question("Hello!")


def llm_thank_you() -> str:
    return ask_question("Thank you!")
