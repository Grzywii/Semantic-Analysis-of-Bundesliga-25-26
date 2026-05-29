from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import pandas as pd
from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef
from rdflib.namespace import XSD


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
ONTOLOGY_PATH = BASE_DIR / "ontologies" / "bundesliga_ontology.ttl"
OUTPUT_PATH = BASE_DIR / "ontologies" / "bundesliga_transformed.ttl"

ONT = Namespace("http://example.org/bundesliga/ontology#")
RES = Namespace("http://example.org/bundesliga/resource/")


def load_csv(name: str) -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / name, dtype=str, encoding="utf-8-sig").fillna("")


def slug(value: str) -> str:
    cleaned = str(value).strip().lower()
    cleaned = cleaned.replace("&", "and")
    cleaned = cleaned.replace("/", "-")
    cleaned = "_".join(cleaned.replace("-", " ").split())
    return quote(cleaned, safe="_")


def resource(kind: str, identifier: str) -> URIRef:
    return URIRef(f"{RES}{kind}/{slug(identifier)}")


def add_literal(
    graph: Graph,
    subject: URIRef,
    predicate: URIRef,
    value: str,
    datatype: URIRef | None = None,
) -> None:
    if value == "":
        return
    graph.add((subject, predicate, Literal(value, datatype=datatype)))


def add_number(
    graph: Graph,
    subject: URIRef,
    predicate: URIRef,
    value: str,
    datatype: URIRef,
) -> None:
    if value == "":
        return
    graph.add((subject, predicate, Literal(value, datatype=datatype)))


def add_date(graph: Graph, subject: URIRef, predicate: URIRef, value: str) -> None:
    if value == "":
        return
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return
    graph.add((subject, predicate, Literal(parsed.date().isoformat(), datatype=XSD.date)))


def add_label(graph: Graph, subject: URIRef, label: str) -> None:
    add_literal(graph, subject, RDFS.label, label)


def country_uri_by_name(countries: pd.DataFrame) -> dict[str, URIRef]:
    mapping: dict[str, URIRef] = {}
    for row in countries.itertuples(index=False):
        uri = resource("country", row.country_id)
        mapping[row.country_name] = uri
    return mapping


def position_uri_by_label(positions: pd.DataFrame) -> dict[str, URIRef]:
    mapping: dict[str, URIRef] = {}
    for row in positions.itertuples(index=False):
        uri = resource("position", row.position_id)
        mapping[row.position_name] = uri
        mapping.setdefault(row.position_group, resource("position", row.position_group))
    return mapping


def add_countries(graph: Graph, countries: pd.DataFrame) -> None:
    for row in countries.itertuples(index=False):
        country = resource("country", row.country_id)
        graph.add((country, RDF.type, ONT.Country))
        add_label(graph, country, row.country_name)
        add_literal(graph, country, ONT.countryName, row.country_name)
        add_literal(graph, country, ONT.continent, row.continent)


def add_positions(graph: Graph, positions: pd.DataFrame) -> None:
    for row in positions.itertuples(index=False):
        position = resource("position", row.position_id)
        graph.add((position, RDF.type, ONT.Position))
        add_label(graph, position, row.position_name)
        add_literal(graph, position, ONT.positionName, row.position_name)
        add_literal(graph, position, ONT.positionGroup, row.position_group)

    for group in sorted(set(positions["position_group"])):
        position = resource("position", group)
        graph.add((position, RDF.type, ONT.Position))
        add_label(graph, position, group)
        add_literal(graph, position, ONT.positionName, group)
        add_literal(graph, position, ONT.positionGroup, group)


def add_seasons(graph: Graph, *frames: pd.DataFrame) -> None:
    seasons = sorted({season for frame in frames for season in frame["season"] if season})
    for season_label in seasons:
        season = resource("season", season_label)
        graph.add((season, RDF.type, ONT.Season))
        add_label(graph, season, season_label)
        add_literal(graph, season, ONT.seasonLabel, season_label)


def add_leagues(graph: Graph, performances: pd.DataFrame) -> None:
    for league_name in sorted(set(performances["league"])):
        if not league_name:
            continue
        league = resource("league", league_name)
        graph.add((league, RDF.type, ONT.League))
        add_label(graph, league, league_name)
        add_literal(graph, league, ONT.leagueName, league_name)


def add_clubs(graph: Graph, clubs: pd.DataFrame, countries_by_name: dict[str, URIRef]) -> None:
    for row in clubs.itertuples(index=False):
        club = resource("club", row.club_id)
        graph.add((club, RDF.type, ONT.Club))
        add_label(graph, club, row.club_name)
        add_literal(graph, club, ONT.clubName, row.club_name)
        add_literal(graph, club, ONT.shortName, row.short_name)
        add_literal(graph, club, ONT.city, row.city)
        add_literal(graph, club, ONT.stadium, row.stadium)

        country = countries_by_name.get(row.country, resource("country", row.country))
        graph.add((club, ONT.basedInCountry, country))


def add_players(
    graph: Graph,
    players: pd.DataFrame,
    countries_by_name: dict[str, URIRef],
    positions_by_label: dict[str, URIRef],
) -> None:
    for row in players.itertuples(index=False):
        player = resource("player", row.player_id)
        graph.add((player, RDF.type, ONT.Player))
        add_label(graph, player, row.full_name)
        add_literal(graph, player, ONT.playerName, row.full_name)
        add_date(graph, player, ONT.birthDate, row.birth_date)
        add_number(graph, player, ONT.age, row.age, XSD.integer)

        nationality = countries_by_name.get(row.nationality, resource("country", row.nationality))
        graph.add((player, ONT.hasNationality, nationality))

        position = positions_by_label.get(row.primary_position, resource("position", row.primary_position))
        graph.add((player, ONT.hasPosition, position))


def add_squad_memberships(
    graph: Graph,
    memberships: pd.DataFrame,
    positions_by_label: dict[str, URIRef],
) -> None:
    for row in memberships.itertuples(index=False):
        membership = resource("squad-membership", row.membership_id)
        player = resource("player", row.player_id)
        club = resource("club", row.club_id)
        season = resource("season", row.season)
        position = positions_by_label.get(row.position, resource("position", row.position))

        graph.add((membership, RDF.type, ONT.SquadMembership))
        add_label(graph, membership, row.membership_id)
        graph.add((player, ONT.hasSquadMembership, membership))
        graph.add((membership, ONT.membershipOfPlayer, player))
        graph.add((membership, ONT.membershipForClub, club))
        graph.add((membership, ONT.membershipInSeason, season))
        graph.add((membership, ONT.hasPosition, position))
        add_number(graph, membership, ONT.marketValueEUR, row.market_value_eur, XSD.decimal)


def add_club_performances(graph: Graph, performances: pd.DataFrame) -> None:
    numeric_properties = {
        "league_position": ONT.leaguePosition,
        "points": ONT.points,
        "matches_played": ONT.matchesPlayed,
        "wins": ONT.wins,
        "draws": ONT.draws,
        "losses": ONT.losses,
        "goals_for": ONT.goalsFor,
        "goals_against": ONT.goalsAgainst,
        "goal_difference": ONT.goalDifference,
        "performance_score": ONT.performanceScore,
    }

    for row in performances.itertuples(index=False):
        performance = resource("club-performance", f"{row.club_id}_{row.season}")
        club = resource("club", row.club_id)
        season = resource("season", row.season)
        league = resource("league", row.league)

        graph.add((performance, RDF.type, ONT.ClubPerformance))
        add_label(graph, performance, f"{row.club_id} {row.season} performance")
        graph.add((club, ONT.hasPerformance, performance))
        graph.add((performance, ONT.performanceInSeason, season))
        graph.add((performance, ONT.playsInLeague, league))
        graph.add((club, ONT.playsInLeague, league))

        row_values = row._asdict()
        for column, predicate in numeric_properties.items():
            datatype = XSD.decimal if column == "performance_score" else XSD.integer
            add_number(graph, performance, predicate, row_values[column], datatype)


def add_financial_records(graph: Graph, financials: pd.DataFrame) -> None:
    numeric_properties = {
        "squad_market_value_eur": ONT.squadMarketValueEUR,
        "transfer_spending_eur": ONT.transferSpendingEUR,
        "transfer_income_eur": ONT.transferIncomeEUR,
        "net_transfer_spending_eur": ONT.netTransferSpendingEUR,
    }

    for row in financials.itertuples(index=False):
        financial_record = resource("financial-record", f"{row.club_id}_{row.season}")
        club = resource("club", row.club_id)
        season = resource("season", row.season)

        graph.add((financial_record, RDF.type, ONT.FinancialRecord))
        add_label(graph, financial_record, f"{row.club_id} {row.season} financial record")
        graph.add((club, ONT.hasFinancialRecord, financial_record))
        graph.add((financial_record, ONT.financialRecordInSeason, season))

        row_values = row._asdict()
        for column, predicate in numeric_properties.items():
            add_number(graph, financial_record, predicate, row_values[column], XSD.decimal)


def build_graph() -> Graph:
    clubs = load_csv("clubs.csv")
    countries = load_csv("countries.csv")
    players = load_csv("players.csv")
    positions = load_csv("positions.csv")
    memberships = load_csv("squad_memberships.csv")
    performances = load_csv("club_season_performance.csv")
    financials = load_csv("club_financials.csv")

    graph = Graph()
    graph.parse(ONTOLOGY_PATH, format="turtle")
    graph.bind("bundesliga", ONT)
    graph.bind("res", RES)

    countries_by_name = country_uri_by_name(countries)
    positions_by_label = position_uri_by_label(positions)

    add_countries(graph, countries)
    add_positions(graph, positions)
    add_seasons(graph, memberships, performances, financials)
    add_leagues(graph, performances)
    add_clubs(graph, clubs, countries_by_name)
    add_players(graph, players, countries_by_name, positions_by_label)
    add_squad_memberships(graph, memberships, positions_by_label)
    add_club_performances(graph, performances)
    add_financial_records(graph, financials)

    return graph


def main() -> None:
    graph = build_graph()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    graph.serialize(destination=OUTPUT_PATH, format="turtle")
    print(f"Saved {len(graph)} triples to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
