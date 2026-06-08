// Ariadne synthetic org-hierarchy seed. Fictional. No real-world entities.
MATCH (n) DETACH DELETE n;

CREATE (hq:Unit {name: 'Directorate-HQ', echelon: 1});
CREATE (ops:Unit {name: 'Operations-Wing', echelon: 2});
CREATE (sig:Unit {name: 'Signals-Cell', echelon: 3});
CREATE (log:Unit {name: 'Logistics-Cell', echelon: 3});
CREATE (site:Site {name: 'Compound-Alpha'});

CREATE (halberd:Person {name: 'Halberd', alias: 'H1', aliases: ['H1']});
CREATE (wren:Person {name: 'Wren', alias: 'W4', aliases: ['W4']});
CREATE (talon:Person {name: 'Talon', alias: 'T2', aliases: ['T2']});
CREATE (osprey:Person {name: 'Osprey', alias: 'O7', aliases: ['O7']});

MATCH (ops:Unit {name:'Operations-Wing'}), (hq:Unit {name:'Directorate-HQ'})
CREATE (ops)-[:REPORTS_TO]->(hq);
MATCH (sig:Unit {name:'Signals-Cell'}), (ops:Unit {name:'Operations-Wing'})
CREATE (sig)-[:REPORTS_TO]->(ops);
MATCH (log:Unit {name:'Logistics-Cell'}), (ops:Unit {name:'Operations-Wing'})
CREATE (log)-[:REPORTS_TO]->(ops);

MATCH (halberd:Person {name:'Halberd'}), (sig:Unit {name:'Signals-Cell'})
CREATE (halberd)-[:MEMBER_OF {role:'Lead'}]->(sig);
MATCH (talon:Person {name:'Talon'}), (sig:Unit {name:'Signals-Cell'})
CREATE (talon)-[:MEMBER_OF {role:'Analyst'}]->(sig);
MATCH (wren:Person {name:'Wren'}), (log:Unit {name:'Logistics-Cell'})
CREATE (wren)-[:MEMBER_OF {role:'Lead'}]->(log);
MATCH (osprey:Person {name:'Osprey'}), (log:Unit {name:'Logistics-Cell'})
CREATE (osprey)-[:MEMBER_OF {role:'Driver'}]->(log);

MATCH (halberd:Person {name:'Halberd'}), (talon:Person {name:'Talon'})
CREATE (halberd)-[:COMMUNICATES_WITH {channel:'voice'}]->(talon);

// Non-obvious link: Halberd and Wren never talk directly, but both units are
// co-located at Compound-Alpha — a 3-hop CO_LOCATED path the analyst would miss.
MATCH (sig:Unit {name:'Signals-Cell'}), (site:Site {name:'Compound-Alpha'})
CREATE (sig)-[:CO_LOCATED]->(site);
MATCH (log:Unit {name:'Logistics-Cell'}), (site:Site {name:'Compound-Alpha'})
CREATE (log)-[:CO_LOCATED]->(site);
