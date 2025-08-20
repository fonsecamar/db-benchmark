if OBJECT_ID('cart','U') is not null
	drop table cart
;
create table cart
(
player_id int not null
, ticket_id uniqueidentifier
, ticket_date datetime
, contest int
, numbers json
);

create or alter procedure sp_cart_ins(
@player_id int
, @ticket_id uniqueidentifier
, @ticket_date datetime
, @contest int
, @numbers json
)
as

insert into cart values (@player_id, @ticket_id, @ticket_date, @contest, @numbers)
;