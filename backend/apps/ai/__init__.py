"""
AI integration for TailorUp.

This package is deliberately framework-free: it contains no Django models and
performs no database access, so it can be unit-tested without a database and
imported from services, management commands, or tests alike.

Layout
------
``exceptions``  application-level errors (never raw provider exceptions)
``providers``   the ``AIProvider`` contract plus Ollama and test doubles
``factory``     maps ``AI_PROVIDER`` to a concrete implementation
``prompts``     prompt construction (kept out of the business logic)
``schemas``    structured output contract and parsing
``validators``  fact protection / hallucination detection
``tailor``      the provider-agnostic ``ResumeTailor`` service
"""
