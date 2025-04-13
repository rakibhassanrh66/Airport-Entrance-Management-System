package airport.entrance.management;

public class Person {
    private String name;
    private int id,num;

    public Person(String name, int id, int num) {
        this.name = name;
        this.id = id;
        this.num = num;
    }

    public String getName() {
        return name;
    }

    public int getId() {
        return id;
    }
    
    public int getNum(){
    
        return num;
    }
}
