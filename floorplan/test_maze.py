from maze import *

test_maze = Maze(13,13)


#test_maze.set_room_state(0,4,0,7,0,False)
#test_maze.set_room_state(10,13,8,13,0,False)
#test_maze.contain_maze()

test_maze.gen_rooms()

#test_maze.sidewinder(1)


test_maze.print_rooms()
test_maze.display()