# MongoDB Data Types - EasyChamp

## Collection Names (ALL lowercase)
- `fixtures` (not Fixture)
- `champs` (not Champ)
- `groups` (not Group)
- `stages` (not Stage)
- `teams` (not Team)
- `players` (not Player)
- `champTeams`
- `champTeamPlayers`
- `events`
- `stageteamstats`

## Fixture Document

```javascript
{
  _id: "75980061-8846-49de-8c5a-dd4ac4520f33",  // STRING (not ObjectId, not UUID)
  id: "C92:fixture:team-a-vs-team-b-0",          // ExternalId (string)
  date: ISODate("2024-10-29T00:00:00Z"),
  homeTeamScore: "5",           // STRING (not int)
  awayTeamScore: "3",           // STRING (not int)
  homePenaltyScore: "2",        // STRING or null
  awayPenaltyScore: "3",        // STRING or null
  homeOvertimeScore: null,
  awayOvertimeScore: null,
  hasPenalties: true,           // bool
  hasOvertime: false,           // bool
  winnerTeamId: "guid-string",  // STRING GUID or null
  matchDay: 1,                  // int
  matchDayName: "1",            // STRING - "1" for group stage, "quarterfinal" for playoffs
  status: 2,                    // int enum: 0=Scheduled, 1=InProgress, 2=Finished
  order: 4,                     // int or null - bracket position (nodeId)
  homeTeam: {
    id: "team-guid",
    champTeamId: "champ-team-guid",
    name: "Team A",
    imageUrl: "https://...",
    sportKind: "Soccer",
    league: "League Name",
    isInternational: false
  },
  awayTeam: { /* same structure */ },
  groupRef: { _id: ObjectId("..."), name: "Group A" },
  stageRef: { _id: ObjectId("..."), name: "Group Stage" },
  champRef: { _id: ObjectId("..."), name: "Tournament" },  // NOTE: _id not Id
  champLeagueRef: { _id: ObjectId("...") },
  periodScores: [{
    Home_score: "2",    // snake_case (not HomeScore)
    Away_score: "3",    // snake_case (not AwayScore)
    Type: "penalties"   // auto-lowercased by API
  }],
  homeSquad: [{
    player: {
      id: "player-guid",
      fullName: "K. Moosa",
      firstName: "K.",
      lastName: "Moosa"
    },
    jerseyNumber: null,
    position: null,
    squadType: 0,
    isPlayed: true
  }],
  awaySquad: [ /* same structure */ ],
  events: [{
    id: "event-guid",
    isHomeEvent: true,
    minute: "5",              // STRING
    eventType: "scorer",      // NOT "goal"
    player: {
      id: "player-guid",
      fullName: "K. Moosa",
      otherFullName: "",      // REQUIRED (can be empty)
      sportKindName: "Soccer"
    },
    assistantPlayer: null,
    description: "Goal by K. Moosa"
  }]
}
```

## Champ Document (TeamRefs)

```javascript
{
  _id: ObjectId("..."),
  name: "Tournament Name",
  teamRefs: [{
    Id: "team-guid",              // NOTE: Id not _id
    Name: "Team A",
    ImageUrl: "https://...",
    ChampTeamId: "champ-team-guid"
  }]
}
```

## Group Document (TeamRefs)

```javascript
{
  _id: ObjectId("..."),
  name: "Group A",
  teamRefs: [{
    Id: "team-guid",
    Name: "Team A",
    ImageUrl: "https://..."
  }]
}
```

## Key Type Differences

| Field | API Input (DTO) | MongoDB Storage |
|-------|-----------------|-----------------|
| Fixture._id | string GUID | string |
| Champ._id | Guid | ObjectId |
| Group._id | Guid | ObjectId |
| Stage._id | Guid | ObjectId |
| Scores | string | string |
| PenaltyScores | string | string |
| PeriodScores field names | Home_score (snake) | Home_score (snake) |
| MatchDayName | string | string |
| Status | int enum | int |
| Order | int | int |
| WinnerTeamId | Guid | string |
