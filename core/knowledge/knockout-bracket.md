# Knockout Bracket System - Technical Reference

## Overview

EasyChamp uses a custom binary tree algorithm to render playoff brackets. The core code is in `ec-webcore-lib/src/utils/knockout.ts` (~750 lines).

## Binary Tree Structure

Nodes are numbered using a left-to-right BFS ordering:

### 4-team bracket (depth=2)
```
    1 (Final)
   / \
  2   3 (Semifinal)
```

### 8-team bracket (depth=3)
```
        1 (Final)
       / \
      2   3 (Semifinal)
     / \ / \
    4  5 6  7 (Quarterfinal)
```

### 16-team bracket (depth=4)
```
                1 (Final)
               / \
              2   3 (Semifinal)
             / \ / \
            4  5 6  7 (Quarterfinal)
           /\ /\ /\ /\
          8 9 ... 14 15 (Round of 16)
```

## Tree Generation Algorithm

### `generateTreeFromStages(stageGroup, disableSort, isThirdPlaceMatch, isQualification, isDoubleElimination, teamsCount)`

1. **Calculate depth**: `Math.ceil(Math.log2(teamsCount))` or from max PLAYOFF_STAGES_ORDER value
2. **Generate empty tree**: `generateTree(depth)` creates binary tree with node IDs
3. **fillTree two-pass algorithm**:
   - **First pass**: Match fixtures where `fixture.order == node.nodeId` (order-based matching)
   - **Second pass**: Sequential fill - fixtures without order placed by depth level
4. **sortTree**: Sort teams alphabetically within each node for display

### PLAYOFF_STAGES_ORDER Mapping

```typescript
{
  round_of_128: 6,
  round_of_64:  5,
  round_of_32:  4,
  round_of_16:  3,
  quarterfinal: 2,
  semifinal:    1,
  final:        0,
  "3rd_place_playoff": 0
}
```

## Critical Requirements for Bracket Rendering

### 1. fixture.order must be set
The `fillTree` first pass matches `fixture.order == node.nodeId`. Without order values, fixtures fall to second pass (sequential fill) which may produce incorrect tree placement.

### 2. matchDayName must match PlayoffStage enum
The `PLAYOFF_STAGES_ORDER` lookup determines which depth level a fixture belongs to. Invalid values cause the fixture to be skipped.

Valid values (lowercase, no hyphens):
- `quarterfinal`
- `semifinal`
- `final`
- `3rd_place_playoff`
- `round_of_16`
- `round_of_32`
- `round_of_64`
- `round_of_128`

### 3. stageGroup.teams must exist
If `stageGroup.teams` is undefined, the component crashes with `TypeError: Cannot read properties of undefined (reading 'teams')`. The code uses optional chaining: `stageGroup.teams?.find(...)`.

### 4. stageGroup.fixtures must have entries
The useMemo guard returns early if `!stageGroup?.fixtures?.length`, showing a "no data" state.

## Byes

Empty nodes in the tree represent byes. Top-seeded teams skip rounds by having their opponents' quarterfinal/early round slots empty.

Example: 8-team bracket with 6 teams (2 byes)
```
        1 (Final)
       / \
      2   3 (Semifinal)
     / \ / \
    4  5 6  7 (Quarterfinal)
         ↑     ↑
       empty  empty = byes for #1 and #2 seeds
```

## React Components

```
Graph.tsx
  ├── useMemo → generateTreeFromStages()
  └── TreeNode.tsx (recursive)
      └── Node.tsx (individual fixture card)
```

## API Quirks

1. **Order field not saved via score endpoint**: `PUT /fixture/{id}/score` → `UpdateFixtureScoreAsync` does NOT process Order. Use MongoDB directly.
2. **MongoDB _id is string**: Not UUID. Query with string values.
3. **ChampRef uses `_id` not `Id`**: When querying fixtures by champ.

## Post-Import Bracket Fix Script

```python
from pymongo import MongoClient

client = MongoClient(MONGODB_URI)
db = client['ec-standings-db']

# Set order values for each playoff fixture
updates = {
    "fixture-id-qf1": {"Order": 4, "MatchDayName": "quarterfinal"},
    "fixture-id-qf2": {"Order": 6, "MatchDayName": "quarterfinal"},
    "fixture-id-sf1": {"Order": 2, "MatchDayName": "semifinal"},
    "fixture-id-sf2": {"Order": 3, "MatchDayName": "semifinal"},
    "fixture-id-final": {"Order": 1, "MatchDayName": "final"},
}

for fixture_id, fields in updates.items():
    result = db.fixtures.update_one(
        {"_id": fixture_id},
        {"$set": fields}
    )
    print(f"Updated {fixture_id}: {result.modified_count}")
```
