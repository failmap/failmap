# Stacking pattern

The stacking pattern is the mechanic that Web Security Map uses to store
historical data. It allows for similar data to exist with gaps and very
fast results to queries that ask "what items exist on this moment".

Properly managing or developing Web Security Map requires understanding of this
pattern. It's not that hard, but doing it wrong might cause inconsistent
data.

This pattern is applied to Urls, Organizations, Coordinates and probably
some others. This is also the reason that we're "building" ratings: this
is a chaching mechanic that helps reducing the logic of the actual data
model when presenting results.

The stacking pattern enforces that data over time is in the same model,
requiring to update very old data to fit the latest version of the model
.

## Why stacking?
We needed a very quick way to retrieve historical data, preferably in a
single query. For example: "What Urls exist on 1 january 2017?", with an
anwer in a split second.

Urls on the internet get published, pulled and republished with
different content. We're able to show that using this solution.

Do note that this is not a solution to see "ALL" changes ever made to
the data: it is not an auditing system. That could still be implemented
on top of this solution.

There are several patterns that make it able to browse through history.
Another obvious example would be "shadow tables" or a "shadow database".

The biggest downside of a shadow solution is maintenance on these tables
and actively creating a legacy codebase (or the ability to understand
older models). We've decided that this would result in even more
complications than stacking: we are forcing ourselves to work with a
single model of a URL instead of several, all of which might
have different formats.

Another way to retain history is to use a stacking pattern where the
administration is done in a separate table. Only by using a join you
would be able to see what is the current information. This solution
often uses similar begin and end datetime columns. It also has a status
flag/column and given it's an extra table, some additional columns can
be added for administrative purposes. Such a table should
be made for every history entity.

Sample of another solution:
https://stackoverflow.com/questions/3874199/how-to-store-historical-data


## Stacking / History Support in Django?
Django itself does not support stacking queries: it does have latest and
 earliest for single record results. An iterative approach does work
perfectly but is much, much slower (although more readable).

The best solution would be Django having support for returning the
latest as a set, we're going to use our solution. (And ask the Django
community to take a look at it, in the hope they annihilate our
solution with something much easier, faster and overall better.)

A runner-up to solve this problem is "Django Simple History". It does
seem to have support for history, but it doesn't show if it also
supports queries like the ones we're using here.


## What is this stacking?

If you've worked with databases, you might have discovered this pattern
a few times before. The most disctinctive features are:
- Possibility of gaps in the data (some things didn't exist then)
- Possibility to change all related properties on any level (first
duplicating them to the new thing)


Consider the following example, which is a stacking pattern applied to
a computer company. To simplify the example, dates show only a month and
year.

| ID | Name  | Created On   | Deleted | Deleted_on  | Deletion_reason           |
|----|-------|--------------|---------|-------------|---------------------------|
| 1  | Apple | jan 1977     | 1       | feb 1977    | add new founders          |
| 2  | Apple | april 1977   | 1       | may 1977    | typos in the name         |
| 3  | Apple | june 1977    | 1       | august 1977 | legal reasons             |
| 4  | Apple | januari 1978 | 1       | march 1978  | blue box made us bankrupt |
| 5  | Apple | april 1978   | 1       | june 1978   | we're outsourcing this    |
| 6  | Apple | august 1978  | 0       |             |                           |


When displaying it over time, you get this result:
The column contains a company name when the company exists.

| Jan '77   | Feb '77    | Mar '77    | Apr '77    | May '77   | Jun '77   | Jul '77   | Aug '77   | ... | Jan '78   | Feb '78   | Mar '78   | Apr '78   | ... | Jun '78   | Aug '78   |
|-----------|------------|------------|------------|-----------|-----------|-----------|-----------|-----|-----------|-----------|-----------|-----------|-----|-----------|-----------|
| Apple (1) | Apple (1)  |            | Apple (2)  | Apple (2) | Apple (3) | Apple (3) | Apple (3) |     | Apple (4) | Apple (4) | Apple (4) | Apple (5) | ... | Apple (5) | Apple (6) |
|           | E-Corp (7) | E-Corp (7) | E-Corp (8) |           |           |           |           |     |           |           |           |           |     |           |           |
|           |            |            |            |           | IBM (9)   |           |           |     |           |           |           |           |     |           |           |


## Model fields

A model that applies the stacking pattern needs at least two fields,
and has some assisting fields for shorthands and administrators. These
are the fields:

* created_on (datetime)
* deleted_on (datetime)

* deleted (boolean) - A short hand to instantly get all existing things
at this moment
* deletion_reason (string) - Explanation for administrators why / how
something was deleted.

These fields can be named differently, for example "is_dead",
"is_dead_since" and "is_dead_reason".

A challenge might be to see what fields, together, make up a stacking
pattern.

## Queries

Reading out historical data is fast when doing it right. As explained
before, this requires a manual implementation (as it is not in the ORM
yet).

After some experimentation (see below), this is the fastest solution
that work in both MySQL and SQLite. It has
not been tested in PostGres.

Here is the magic:

```sql
SELECT ... some data and joins ...
FROM map_organizationrating
INNER JOIN
    (SELECT MAX(id) as id2 FROM map_organizationrating or2
    WHERE `when` <= '%s' GROUP BY organization_id) as x
    ON x.id2 = map_organizationrating.id
```

It simply is a subquery on the "what are the newest on this moment", allowing you to filter on the
result set outside this subquery.


## Speed improvements

Aside from returning the correct results, we've found that it improves times for these operations:

Terrible Urls: from 0.5 seconds to (0.3 / 0.0 seconds)
Top Fail: from 0.5 seconds to 0.0 seconds



## Queries that didn't work:

Coming up with this solution, various options have been tried. For reference (to save you time) these
are described below, with a complete example query.

### Original Query
This query does not produce the correct results in MySQL, but it does in SQLlite. This was weird at first
but it's understandable given MySQL first does ordering, while SQLlite does Having and Group first. The results
are very different. It was extremly fast given it doesn't do anything "weird".

```python
sql = '''
 SELECT
        rating,
        organization.name,
        organizations_organizationtype.name,
        coordinate.area,
        coordinate.geoJsonType,
        organization.id
    FROM map_organizationrating
    INNER JOIN
      organization on organization.id = map_organizationrating.organization_id
    INNER JOIN
      organizations_organizationtype on organizations_organizationtype.id = organization.type_id
    INNER JOIN
      coordinate ON coordinate.organization_id = organization.id
    WHERE `when` <= '%s'
    GROUP BY coordinate.area
    HAVING MAX(`when`)
    ORDER BY `when` ASC'''  % (when, )
```

### Filtering in Where
Doing the desired filtering in a where query is possible, but it's slow. The query took 0.7 seconds to
run on the testdata, which is an eternity in SQL time.

```python
sql = '''
    SELECT
        rating,
        organization.name,
        organizations_organizationtype.name,
        coordinate.area,
        coordinate.geoJsonType,
        organization.id
    FROM map_organizationrating
    INNER JOIN
      organization on organization.id = map_organizationrating.organization_id
    INNER JOIN
      organizations_organizationtype on organizations_organizationtype.id = organization.type_id
    INNER JOIN
      coordinate ON coordinate.organization_id = organization.id
    WHERE `when` = (select MAX(`when`) FROM map_organizationrating or2
          WHERE or2.organization_id = map_organizationrating.organization_id AND
          `when` <= '2017-08-14 18:21:36.984601+00:00')
    GROUP BY coordinate.area
    ORDER BY `when` ASC
    ''' % (when, )
```

### In Query in Where
"IN" is another semantically correct solution, but not implemented as optimal everywhere. On the testdata
this query delivered the correct result but took 2 minutes and 4.54 seconds to run. Totally not acceptable.

```python
sql = '''
    SELECT
        rating,
        organization.name,
        organizations_organizationtype.name,
        coordinate.area,
        coordinate.geoJsonType,
        organization.id
    FROM map_organizationrating
    INNER JOIN
      organization on organization.id = map_organizationrating.organization_id
    INNER JOIN
      organizations_organizationtype on organizations_organizationtype.id = organization.type_id
    INNER JOIN
      coordinate ON coordinate.organization_id = organization.id
    WHERE map_organizationrating.id IN (
      SELECT DISTINCT MAX(id) FROM failmap.map_organizationrating
      WHERE `when` <= '%s' GROUP BY organization_id)
    GROUP BY coordinate.area
    ORDER BY `when` ASC
    ''' % (when, )
```

### The fastest and correct query
After some thinking this is the fasted solution, with the correct result in 0.16 seconds which the
database also caches on a consecutive run, where 0.01 second is needed to return the result.

It works in both MySQL and SQLite and returns the same (correct) answer:

```python
sql = '''
    SELECT
        rating,
        organization.name,
        organizations_organizationtype.name,
        coordinate.area,
        coordinate.geoJsonType,
        organization.id,
        calculation,
        high,
        medium,
        low
    FROM map_organizationrating
    INNER JOIN
      organization on organization.id = map_organizationrating.organization_id
    INNER JOIN
      organizations_organizationtype on organizations_organizationtype.id = organization.type_id
    INNER JOIN
      coordinate ON coordinate.organization_id = organization.id
    INNER JOIN
      (SELECT MAX(id) as id2 FROM map_organizationrating or2
      WHERE `when` <= '%s' GROUP BY organization_id) as x
      ON x.id2 = map_organizationrating.id
    GROUP BY coordinate.area, organization.name
    ORDER BY `when` ASC
    ''' % (when, )
```
