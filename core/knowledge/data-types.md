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
  periodScores: [
    // IMPORTANT: Import JSON uses PascalCase (HomeScore/AwayScore) but
    // MongoDB stores snake_case (Home_score/Away_score). AutoMapper mapping
    // was fixed 2026-02-12 to handle this conversion explicitly.
    // Frontend reads penalties from: periodScores.find(x => x.type === "penalties")
    {
      Home_score: "4",    // snake_case in MongoDB (mapped from PascalCase in import)
      Away_score: "4",    // Full-time score
      Type: "regular_period",
      Number: 1
    },
    {
      Home_score: "2",    // Penalty shootout score
      Away_score: "3",
      Type: "penalties",  // MUST be lowercase "penalties"
      Number: 2
    }
  ],
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

| Field | Import Model (JSON) | DTO (C#) | MongoDB Storage |
|-------|---------------------|----------|-----------------|
| Fixture._id | string GUID | string GUID | string |
| Champ._id | string | Guid | ObjectId |
| Group._id | string | Guid | ObjectId |
| Stage._id | string | Guid | ObjectId |
| Scores | string | string | string |
| PenaltyScores | string | string | string |
| PeriodScores.HomeScore | **HomeScore** (PascalCase) | **Home_score** (snake) | Home_score (snake) |
| PeriodScores.AwayScore | **AwayScore** (PascalCase) | **Away_score** (snake) | Away_score (snake) |
| MatchDayName | string | string | string |
| Status | int enum | int enum | int |
| Order | int | int | int |
| WinnerTeamId | string | Guid | string |

**CRITICAL**: PeriodScores field names differ between import JSON and DTO/MongoDB.
AutoMapper explicit mapping required (added 2026-02-12):
```csharp
CreateMap<PeriodScore, PeriodScoreDto>()
    .ForMember(dest => dest.Home_score, source => source.MapFrom(s => s.HomeScore))
    .ForMember(dest => dest.Away_score, source => source.MapFrom(s => s.AwayScore));
```

## Backend Import Service Bugs (Fixed)

| Bug | File | Fix Date | Description |
|-----|------|----------|-------------|
| ChampTeamId missing | ImportLeagueService.cs:294 | 2026-02-12 | `eventDto.ChampTeamId` never set - events created with Guid.Empty |
| PeriodScore mapping | ApiCoreImportEntityProfile.cs | 2026-02-12 | PascalCase→snake_case mismatch - scores stored as null |
| Team update dead code | ImportTeamsService.cs:74-93 | 2026-02-12 | Update branch unreachable - teams never updated on reimport |
