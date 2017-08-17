use music;
select page,name,artist,sum(times),score 
from plays inner join pages on (page=pages.uid) 
group by page 
having score<>sum(times);